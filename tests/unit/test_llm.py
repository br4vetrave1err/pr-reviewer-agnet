# Implements: UTP-012-A, UTS-012-A1, UTS-012-A2, MOD-012, ARCH-008, REQ-009
"""Unit tests — MOD-012 (LLM Security Reviewer)."""

import pytest

from domain import Finding, ReviewResult, Severity
from security.llm import LlmSecurityReviewer, SecurityContext


class FakeRunner:
    def __init__(self, result):
        self._result = result
        self.prompt = None

    async def security_step(self, prompt):
        self.prompt = prompt
        return self._result


def test_uts_012_a1_llm_findings_normalized():
    runner = FakeRunner(
        ReviewResult(
            summary="sec",
            findings=[
                Finding(path="app.py", line=10, severity=Severity.HIGH, title="Injection", type="security")
            ],
        )
    )
    reviewer = LlmSecurityReviewer(runner)
    ctx = SecurityContext(diff="code", tool_findings=[], docs_text="")
    result = reviewer._cap_findings(runner._result)
    assert result.findings[0].path == "app.py"
    assert result.findings[0].line == 10
    assert result.findings[0].severity == Severity.HIGH


@pytest.mark.asyncio
async def test_uts_012_a2_provider_timeout_degrades_gracefully():
    runner = FakeRunner(ReviewResult(exit_code=124, retryable=True))
    reviewer = LlmSecurityReviewer(runner)
    result = await reviewer.review(SecurityContext(diff="d", tool_findings=[]))
    assert result.retryable is True  # degrade, no raise


def test_build_prompt_includes_tool_findings():
    runner = FakeRunner(ReviewResult())
    reviewer = LlmSecurityReviewer(runner)
    ctx = SecurityContext(
        diff="+++ code",
        tool_findings=[Finding(path="x", severity=Severity.HIGH, title="Secret", type="secrets")],
    )
    prompt = reviewer.build_prompt(ctx)
    assert "x" in prompt
    assert "Secret" in prompt
