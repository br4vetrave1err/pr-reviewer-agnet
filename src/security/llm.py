# Implements: MOD-012, ARCH-008, SYS-008, REQ-009, ARCH-006
"""LLM Security Reviewer (MOD-012 / ARCH-008).

Runs INSIDE the single ``opencode run`` session (MOD-008) â€” the /code-review
prompt includes a security step; no separate model call. This module builds
the security context from the diff + tool findings and parses the findings
back out. A failed LLM call is retryable and degrades the security phase
(ARCH-006).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from domain import Finding, ReviewResult, Severity

log = logging.getLogger("pr_reviewer.security.llm")


@dataclass
class SecurityContext:
    diff: str
    tool_findings: list[Finding]
    docs_text: str = ""


class LlmSecurityReviewer:
    def __init__(self, workspace_runner, findings_cap: int = 50):
        self._runner = workspace_runner
        self._cap = findings_cap

    def build_prompt(self, context: SecurityContext) -> str:
        tool_lines = "\n".join(
            f"- {f.path}:{f.line or '?'} {f.title} ({f.detail})" for f in context.tool_findings
        )
        return (
            "Security review step. Review this diff for security issues "
            "(injection, auth bypass, secrets handling, unsafe deserialization, "
            "dependency risks). Return JSON with findings.\n\n"
            f"=== TOOL FINDINGS ===\n{tool_lines or 'none'}\n"
            f"=== DIFF ===\n{context.diff}\n"
        )

    async def review(self, context: SecurityContext) -> ReviewResult:
        result = await self._runner.security_step(self.build_prompt(context))
        if result.retryable:
            log.warning("LLM security step failed; retryable")
            return result
        return self._cap_findings(result)

    def _cap_findings(self, result: ReviewResult) -> ReviewResult:
        if len(result.findings) <= self._cap:
            return result
        return ReviewResult(
            summary=result.summary,
            findings=result.findings[: self._cap],
            exit_code=result.exit_code,
            retryable=result.retryable,
        )
