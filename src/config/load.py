# Implements: MOD-016, ARCH-012, SYS-013, REQ-IF-004, REQ-016, REQ-017, REQ-CN-001
"""Config loader and validator (MOD-016 / ARCH-012).

Loads ``config.yaml`` and validates it fail-closed. Invalid configuration
raises :class:`ConfigError` and the service refuses to boot
(REQ-IF-004, SCN-IF-004-A2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


class ConfigError(Exception):
    """Raised when config.yaml is missing, malformed, or invalid."""


@dataclass
class ProviderSpec:
    provider: str
    model: str
    enabled: bool = True
    auth_env: Optional[str] = None


@dataclass
class RepoSpec:
    owner: str
    repo: str
    default_model: Optional[str] = None
    enabled: bool = True
    require_approval: bool = False
    auto_merge: bool = True


@dataclass
class CiGateSpec:
    enabled: bool = True
    settle_seconds: int = 75
    wait_cap_minutes: int = 60


@dataclass
class RetrySpec:
    max_attempts: int = 3
    backoff_seconds: list[int] = field(default_factory=lambda: [30, 120])


@dataclass
class AgentSkillSet:
    base: str = "/code-review"
    situational: list[str] = field(default_factory=lambda: ["/diagnosing-bugs", "/resolving-merge-conflicts"])


@dataclass
class RunnerSpec:
    type: str = "opencode"
    binary: str = "opencode"


@dataclass
class Config:
    providers: dict[str, ProviderSpec] = field(default_factory=dict)
    default_model: str = "free"
    switch_default: Optional[str] = None
    repo_config: list[RepoSpec] = field(default_factory=list)
    denylist: list[str] = field(default_factory=list)
    concurrency: int = 1
    disk_cap_bytes: int = 10 * 1024 * 1024 * 1024
    validator_filter_enabled: bool = True
    ci_gate: CiGateSpec = field(default_factory=CiGateSpec)
    reconcile_interval_seconds: int = 300
    retry: RetrySpec = field(default_factory=RetrySpec)
    specs_docs_dir: str = "specs"
    workspace_cache_dir: str = "/var/agent_cache/repos"
    ngrok_agent_url: str = "http://ngrok:4040"
    agent_skill_set: AgentSkillSet = field(default_factory=AgentSkillSet)
    runner: RunnerSpec = field(default_factory=RunnerSpec)
    webhook_secret_env: str = "WEBHOOK_SECRET"
    github_token_env: str = "GITHUB_TOKEN"

    def is_managed(self, owner: str, repo: str) -> bool:
        """REQ-003: only repos listed in repo_config are managed."""
        return any(r.owner == owner and r.repo == repo and r.enabled for r in self.repo_config)

    def is_denied(self, owner: str, repo: str) -> bool:
        return f"{owner}/{repo}" in self.denylist

    def alias_enabled(self, alias: str) -> bool:
        prov = self.providers.get(alias)
        return bool(prov and prov.enabled)

    def get_repo_spec(self, owner: str, repo: str) -> Optional[RepoSpec]:
        return next((r for r in self.repo_config if r.owner == owner and r.repo == repo), None)

    def requires_approval(self, owner: str, repo: str) -> bool:
        spec = self.get_repo_spec(owner, repo)
        return spec.require_approval if spec else False

    def can_auto_merge(self, owner: str, repo: str) -> bool:
        spec = self.get_repo_spec(owner, repo)
        if spec and spec.require_approval:
            return False
        return spec.auto_merge if spec else False


def validate(raw: Any) -> Config:
    """Validate a parsed config mapping and return a typed Config.

    Fail-closed: any structural violation raises :class:`ConfigError`.
    """
    if not isinstance(raw, dict):
        raise ConfigError("config.yaml must be a mapping")

    errors: list[str] = []

    providers_raw = raw.get("providers")
    if not isinstance(providers_raw, dict) or not providers_raw:
        errors.append("providers must be a non-empty mapping")
        providers_raw = {}

    providers: dict[str, ProviderSpec] = {}
    for alias, spec in (providers_raw or {}).items():
        if not isinstance(spec, dict):
            errors.append(f"providers.{alias} must be a mapping")
            continue
        if not spec.get("provider"):
            errors.append(f"providers.{alias}.provider is required")
        if not spec.get("model"):
            errors.append(f"providers.{alias}.model is required")
        providers[alias] = ProviderSpec(
            provider=str(spec.get("provider", "")),
            model=str(spec.get("model", "")),
            enabled=bool(spec.get("enabled", True)),
            auth_env=spec.get("auth_env"),
        )

    default_model = raw.get("default_model", "free")
    if default_model not in providers:
        errors.append("default_model must be a defined provider alias (REQ-016)")
    elif not providers[default_model].enabled:
        errors.append("default_model must reference an enabled alias (REQ-016)")

    switch_default = raw.get("switch_default")
    if switch_default is not None and switch_default not in providers:
        errors.append("switch_default must be a defined provider alias (REQ-016)")

    repo_config_raw = raw.get("repo_config")
    if not isinstance(repo_config_raw, list) or not repo_config_raw:
        errors.append("repo_config must list at least one managed repo (REQ-003)")
    repo_config: list[RepoSpec] = []
    for entry in (repo_config_raw or []):
        if not isinstance(entry, dict) or not entry.get("owner") or not entry.get("repo"):
            errors.append("repo_config entries need owner and repo")
            continue
        repo_config.append(
            RepoSpec(
                owner=str(entry["owner"]),
                repo=str(entry["repo"]),
                default_model=entry.get("default_model"),
                enabled=bool(entry.get("enabled", True)),
                require_approval=bool(entry.get("require_approval", False)),
                auto_merge=bool(entry.get("auto_merge", True)),
            )
        )

    denylist = raw.get("denylist", [])
    if not isinstance(denylist, list):
        errors.append("denylist must be a list")

    ci_gate_raw = raw.get("ci_gate", {}) or {}
    ci_gate = CiGateSpec(
        enabled=bool(ci_gate_raw.get("enabled", True)),
        settle_seconds=int(ci_gate_raw.get("settle_seconds", 75)),
        wait_cap_minutes=int(ci_gate_raw.get("wait_cap_minutes", 60)),
    )

    defaults_raw = raw.get("defaults", {}) or {}
    retry_raw = raw.get("retry", {}) or {}

    agent_skill_raw = raw.get("agent_skill_set", {}) or {}
    base_skill = agent_skill_raw.get("base", "/code-review")
    situational = agent_skill_raw.get("situational", ["/diagnosing-bugs", "/resolving-merge-conflicts"])
    if not isinstance(situational, list):
        errors.append("agent_skill_set.situational must be a list (REQ-017)")
        situational = []
    agent_skill_set = AgentSkillSet(base=str(base_skill), situational=[str(s) for s in situational])

    runner_raw = raw.get("runner", {}) or {}
    runner_type = str(runner_raw.get("type", "antigravity"))
    runner_bin = str(runner_raw.get("binary", "agy" if runner_type in {"antigravity", "agy"} else "opencode"))
    runner = RunnerSpec(type=runner_type, binary=runner_bin)

    webhook_secret = raw.get("webhook_secret")
    if webhook_secret is not None and len(str(webhook_secret)) < 16:
        errors.append("webhook_secret must be at least 16 characters")

    if errors:
        raise ConfigError("; ".join(errors))

    return Config(
        providers=providers,
        default_model=str(default_model),
        switch_default=switch_default,
        repo_config=repo_config,
        denylist=[str(d) for d in denylist],
        concurrency=int(defaults_raw.get("concurrency", 1)),
        disk_cap_bytes=int(defaults_raw.get("disk_cap_bytes", 10 * 1024 * 1024 * 1024)),
        validator_filter_enabled=bool(defaults_raw.get("validator_filter_enabled", True)),
        ci_gate=ci_gate,
        reconcile_interval_seconds=int(raw.get("reconcile_interval_seconds", 300)),
        retry=RetrySpec(
            max_attempts=int(retry_raw.get("max_attempts", 3)),
            backoff_seconds=[int(b) for b in retry_raw.get("backoff_seconds", [30, 120])],
        ),
        specs_docs_dir=str(raw.get("specs_docs_dir", "specs")),
        workspace_cache_dir=str(raw.get("workspace_cache_dir", "/var/agent_cache/repos")),
        ngrok_agent_url=str(raw.get("ngrok_agent_url", "http://ngrok:4040")),
        agent_skill_set=agent_skill_set,
        runner=runner,
        webhook_secret_env=str(raw.get("webhook_secret_env", "WEBHOOK_SECRET")),
        github_token_env=str(raw.get("github_token_env", "GITHUB_TOKEN")),
    )


def load_config(path: str | Path) -> Config:
    """Load and validate config.yaml at *path* (ARCH-012 load contract)."""
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"config file not found: {path}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"config.yaml is not valid YAML: {exc}") from exc
    return validate(raw)
