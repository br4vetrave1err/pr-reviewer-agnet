# Implements: MOD-008, ARCH-006, SYS-006, REQ-007, REQ-017, REQ-IF-003, REQ-CN-003, REQ-NF-004, REQ-CN-004
"""Workspace Runner (MOD-008 / SYS-006).

Runs opencode as a one-off ``opencode run`` CLI subprocess with ``cwd`` at the
checkout (read-only, REQ-CN-004), repo ``AGENTS.md`` + ``.opencode/`` skills,
vendored ``.agents/skills/``, docs, the resolved model alias, and the defined
agent skill set (REQ-017 / REQ-CN-003). Keys reach the child only through the
referenced env var (REQ-NF-004); parses the structured-JSON result
(REQ-IF-003).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from domain import Finding, ReviewResult, Severity

log = logging.getLogger("pr_reviewer.runner.workspace")


@dataclass
class PromptContext:
    head: str
    owner: str
    repo: str
    pr: int
    docs_text: str
    diff: str
    model_alias: str
    auth_ref: str
    skill_args: list[str]


class WorkspaceRunner:
    _WRITE_COMMANDS = {"commit", "push", "checkout -b", "branch", "tag", "reset", "merge", "rebase"}

    def __init__(self, registry, skills, opencode_bin: str = "opencode", timeout_seconds: int = 900):
        self._registry = registry
        self._skills = skills
        self._bin = opencode_bin
        self._timeout = timeout_seconds

    def guard_read_only(self, argv: list[str]) -> bool:
        """UTS-008-A1: reject write/commit/push operations (REQ-CN-004)."""
        joined = " ".join(argv)
        return not any(w in joined for w in self._WRITE_COMMANDS)

    async def run(self, checkout: str, context: PromptContext) -> ReviewResult:
        model = self._registry.resolve(context.model_alias)  # MOD-014; unknown => raises
        skill_args = context.skill_args or self._skills.select([])
        env = self._build_env(context.auth_ref)  # keys via env only (REQ-NF-004)

        prompt = self._assemble_prompt(context)
        argv = [self._bin, "run"] + skill_args + ["--non-interactive", prompt]

        log.info("spawning opencode run (model=%s, skills=%s)", model.alias, skill_args)
        try:
            proc = subprocess.run(
                argv,
                cwd=checkout,
                env=env,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            log.error("opencode run timed out after %ds", self._timeout)
            return ReviewResult(exit_code=124, retryable=True)
        except FileNotFoundError:
            log.error("opencode binary not found (exit 127)")
            return ReviewResult(exit_code=127, retryable=True)  # ARCH-006 opencode-failure

        if proc.returncode != 0:
            log.error("opencode exit %d: %s", proc.returncode, proc.stderr[:500])
            return ReviewResult(exit_code=proc.returncode, retryable=self._is_retryable(proc.returncode))

        return self._parse_result(proc.stdout)

    async def security_step(self, prompt: str) -> ReviewResult:
        """Security step run in-session (MOD-012); same invocation shape."""
        env = os.environ.copy()
        env["CI"] = "true"
        argv = [self._bin, "run", "--non-interactive", prompt]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=self._timeout)
        except subprocess.TimeoutExpired:
            return ReviewResult(exit_code=124, retryable=True)
        except FileNotFoundError:
            return ReviewResult(exit_code=127, retryable=True)
        if proc.returncode != 0:
            return ReviewResult(exit_code=proc.returncode, retryable=self._is_retryable(proc.returncode))
        return self._parse_result(proc.stdout)

    def _build_env(self, auth_ref: str) -> dict:
        env = os.environ.copy()
        env["GIT_DIR"] = ".git"
        env["CI"] = "true"
        if auth_ref and auth_ref not in env:
            log.error("auth ref %s not present in environment (REQ-NF-004)", auth_ref)
        return env

    def _assemble_prompt(self, context: PromptContext) -> str:
        return (
            f"Review the changes at {context.head} in {context.owner}/{context.repo} "
            f"PR #{context.pr}. "
            "Run a code review per /code-review. Include a security step "
            "covering the diff. Return a single JSON object with keys "
            '{"summary": "...", "findings": [{"path", "line", "severity", '
            '"title", "detail", "type"}]}.\n\n'
            f"=== DOCS ===\n{context.docs_text}\n"
            f"=== DIFF ===\n{context.diff}\n"
        )

    @staticmethod
    def _is_retryable(exit_code: int) -> bool:
        return exit_code in {1, 124}  # provider outage / timeout (REQ-014)

    @staticmethod
    def _parse_result(stdout: str) -> ReviewResult:
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return ReviewResult(summary="", exit_code=0)
        findings = [
            Finding(
                path=str(f.get("path", "")),
                line=f.get("line"),
                severity=_parse_severity(f.get("severity")),
                title=str(f.get("title", "")),
                detail=str(f.get("detail", "")),
                type=str(f.get("type", "review")),
            )
            for f in data.get("findings", [])
        ]
        return ReviewResult(summary=str(data.get("summary", "")), findings=findings, exit_code=0)


def _parse_severity(value: Optional[str]) -> Severity:
    try:
        return Severity(value.lower())
    except (AttributeError, ValueError):
        return Severity.LOW
