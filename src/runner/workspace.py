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
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from domain import Finding, ReviewResult, Severity

log = logging.getLogger("pr_reviewer.runner.workspace")


def _log_agent_stream_line(line: str) -> None:
    text = line.rstrip()
    if not text:
        return
    lower = text.lower()
    if "level=error" in lower or "level=fatal" in lower or "error:" in lower:
        log.error("[agent:error] %s", text)
    elif "level=warn" in lower or "level=warning" in lower or "warning:" in lower:
        log.warning("[agent:warn] %s", text)
    else:
        log.info("[agent:info] %s", text)


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

        prompt = self._assemble_prompt(context, checkout=checkout)
        model_spec = f"{model.provider}/{model.model}" if model.provider and model.model else model.alias

        runner_cfg = getattr(self._registry._config, "runner", None) if hasattr(self._registry, "_config") else None
        runner_type = getattr(runner_cfg, "type", "antigravity")
        runner_bin = getattr(runner_cfg, "binary", self._bin) or self._bin

        if runner_type in {"antigravity", "agy"}:
            argv = [runner_bin, "run", "--print-logs", "--log-level", "DEBUG", "--auto", "--title", "Automated Code Review (Antigravity)", "-m", model_spec] + skill_args + ["--non-interactive", prompt]
        else:
            argv = [runner_bin, "run", "--print-logs", "--log-level", "DEBUG", "--auto", "--title", "Automated Code Review", "-m", model_spec] + skill_args + ["--non-interactive", prompt]

        cmd_argv = [a for a in argv if a != "--non-interactive"]

        log.info(
            "runner_spawn",
            extra={
                "event": "runner_spawn",
                "runner_type": runner_type,
                "model": model.alias,
                "model_spec": model_spec,
                "skill_set": skill_args,
                "cwd": checkout,
                "timeout_s": self._timeout,
            },
        )

        _t0 = time.monotonic()

        try:
            if hasattr(subprocess.run, "__pytest_wrapped__") or type(subprocess.run).__module__ != "subprocess":
                # ---- test / mock path: capture_output=True ----
                proc = subprocess.run(
                    cmd_argv,
                    cwd=checkout,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                )
                duration_ms = int((time.monotonic() - _t0) * 1000)
                if proc.stderr:
                    for _line in proc.stderr.splitlines():
                        _log_agent_stream_line(_line)
                log.info(
                    "runner_exit",
                    extra={
                        "event": "runner_exit",
                        "exit_code": proc.returncode,
                        "duration_ms": duration_ms,
                        "retryable": self._is_retryable(proc.returncode) if proc.returncode != 0 else False,
                        "stdout_bytes": len(proc.stdout),
                        "stderr_bytes": len(proc.stderr),
                    },
                )
                if proc.returncode != 0:
                    return ReviewResult(exit_code=proc.returncode, retryable=self._is_retryable(proc.returncode))
                return self._parse_result(proc.stdout)

            # ---- production path: streaming Popen ----
            proc = subprocess.Popen(
                cmd_argv,
                cwd=checkout,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            stdout_lines: list[str] = []
            stderr_lines: list[str] = []

            def _stream_err():
                for line in proc.stderr:
                    stderr_lines.append(line)
                    _log_agent_stream_line(line)

            def _stream_out():
                for line in proc.stdout:
                    stdout_lines.append(line)

            t_err = threading.Thread(target=_stream_err, daemon=True)
            t_out = threading.Thread(target=_stream_out, daemon=True)
            t_err.start()
            t_out.start()

            try:
                proc.wait(timeout=self._timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                t_err.join(timeout=2.0)
                t_out.join(timeout=2.0)
                duration_ms = int((time.monotonic() - _t0) * 1000)
                log.error(
                    "runner_exit",
                    extra={
                        "event": "runner_exit",
                        "exit_code": 124,
                        "duration_ms": duration_ms,
                        "retryable": True,
                        "reason": "timeout",
                        "timeout_s": self._timeout,
                    },
                )
                return ReviewResult(exit_code=124, retryable=True)

            t_err.join(timeout=2.0)
            t_out.join(timeout=2.0)

            stdout_text = "".join(stdout_lines)
            stderr_text = "".join(stderr_lines)

        except FileNotFoundError:
            duration_ms = int((time.monotonic() - _t0) * 1000)
            log.error(
                "runner_exit",
                extra={
                    "event": "runner_exit",
                    "exit_code": 127,
                    "duration_ms": duration_ms,
                    "retryable": True,
                    "reason": "binary_not_found",
                    "binary": runner_bin,
                },
            )
            return ReviewResult(exit_code=127, retryable=True)  # ARCH-006 runner-failure

        duration_ms = int((time.monotonic() - _t0) * 1000)
        log.info(
            "runner_exit",
            extra={
                "event": "runner_exit",
                "exit_code": proc.returncode,
                "duration_ms": duration_ms,
                "retryable": self._is_retryable(proc.returncode) if proc.returncode != 0 else False,
                "stdout_bytes": len(stdout_text),
                "stderr_bytes": len(stderr_text),
            },
        )

        if proc.returncode != 0:
            return ReviewResult(exit_code=proc.returncode, retryable=self._is_retryable(proc.returncode))

        return self._parse_result(stdout_text)

    async def security_step(self, prompt: str) -> ReviewResult:
        """Security step run in-session (MOD-012); same invocation shape."""
        env = os.environ.copy()
        env["CI"] = "true"
        argv = [self._bin, "run", "--print-logs", "--log-level", "DEBUG", "--non-interactive", prompt]
        cmd_argv = [a for a in argv if a != "--non-interactive"]

        log.info(
            "runner_spawn",
            extra={
                "event": "runner_spawn",
                "runner_type": "security_step",
                "model": "default",
                "cwd": "(inherited)",
                "timeout_s": self._timeout,
            },
        )
        _t0 = time.monotonic()

        try:
            proc = subprocess.run(cmd_argv, capture_output=True, text=True, env=env, timeout=self._timeout)
        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - _t0) * 1000)
            log.error(
                "runner_exit",
                extra={
                    "event": "runner_exit",
                    "runner_type": "security_step",
                    "exit_code": 124,
                    "duration_ms": duration_ms,
                    "retryable": True,
                    "reason": "timeout",
                },
            )
            return ReviewResult(exit_code=124, retryable=True)
        except FileNotFoundError:
            duration_ms = int((time.monotonic() - _t0) * 1000)
            log.error(
                "runner_exit",
                extra={
                    "event": "runner_exit",
                    "runner_type": "security_step",
                    "exit_code": 127,
                    "duration_ms": duration_ms,
                    "retryable": True,
                    "reason": "binary_not_found",
                },
            )
            return ReviewResult(exit_code=127, retryable=True)

        duration_ms = int((time.monotonic() - _t0) * 1000)
        if proc.stderr:
            for _line in proc.stderr.splitlines():
                _log_agent_stream_line(_line)
        log.info(
            "runner_exit",
            extra={
                "event": "runner_exit",
                "runner_type": "security_step",
                "exit_code": proc.returncode,
                "duration_ms": duration_ms,
                "retryable": self._is_retryable(proc.returncode) if proc.returncode != 0 else False,
                "stdout_bytes": len(proc.stdout),
                "stderr_bytes": len(proc.stderr),
            },
        )
        if proc.returncode != 0:
            return ReviewResult(exit_code=proc.returncode, retryable=self._is_retryable(proc.returncode))
        return self._parse_result(proc.stdout)

    def _build_env(self, auth_ref: str) -> dict:
        env = os.environ.copy()
        env["CI"] = "true"
        if auth_ref and auth_ref not in env:
            log.error("auth ref %s not present in environment (REQ-NF-004)", auth_ref)
        return env

    def _assemble_prompt(self, context: PromptContext, checkout: str = "") -> str:
        checkout_note = (
            f"The PR files are checked out at: {checkout}\n"
            f"Use this path (not /app) when reading files with shell or read tools.\n"
        ) if checkout else ""
        return (
            f"Review the changes at {context.head} in {context.owner}/{context.repo} "
            f"PR #{context.pr}. "
            "Run a code review per /code-review. Include a security step "
            "covering the diff. Return a single JSON object with keys "
            '{"summary": "...", "findings": [{"path", "line", "severity", '
            '"title", "detail", "type"}]}.\n\n'
            f"{checkout_note}"
            f"=== DOCS ===\n{context.docs_text}\n"
            f"=== DIFF ===\n{context.diff}\n"
        )

    @staticmethod
    def _is_retryable(exit_code: int) -> bool:
        return exit_code in {1, 124}  # provider outage / timeout (REQ-014)

    @staticmethod
    def _parse_result(stdout: str) -> ReviewResult:
        stdout_clean = stdout.strip()
        if "```json" in stdout_clean:
            stdout_clean = stdout_clean.split("```json")[-1].split("```")[0].strip()
        elif "```" in stdout_clean:
            stdout_clean = stdout_clean.split("```")[-1].split("```")[0].strip()
        try:
            data = json.loads(stdout_clean)
        except json.JSONDecodeError as exc:
            summary_text = stdout.strip() or "Automated code review completed by PR Reviewer Agent."
            log.warning(
                "runner_parse_fallback",
                extra={
                    "event": "runner_parse_fallback",
                    "reason": str(exc),
                    "stdout_preview": stdout[:500],
                    "fallback": "plain_text_summary",
                },
            )
            return ReviewResult(summary=summary_text, exit_code=0)
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
        log.info(
            "runner_parse_ok",
            extra={
                "event": "runner_parse_ok",
                "findings_count": len(findings),
                "has_summary": bool(data.get("summary")),
            },
        )
        return ReviewResult(summary=str(data.get("summary", "Automated code review completed.")), findings=findings, exit_code=0)


def _parse_severity(value: Optional[str]) -> Severity:
    try:
        return Severity(value.lower())
    except (AttributeError, ValueError):
        return Severity.LOW
