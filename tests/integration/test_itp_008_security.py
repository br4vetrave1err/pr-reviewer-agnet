# Implements: ITP-008-A, ARCH-008, REQ-009
"""ITP-008-A: gitleaks and LLM security phases feed one normalized findings list."""

import subprocess

import pytest

from domain import Finding, ReviewResult, Severity
from security.llm import LlmSecurityReviewer, SecurityContext
from security.scanner import SecurityScanRunner


class _Gitleaks:
    def __init__(self, out, rc=1):
        self.out = out
        self.rc = rc
        self.called = False

    def __call__(self, argv, **kw):
        self.called = True
        return _Proc(self.rc, self.out)


class _Proc:
    def __init__(self, rc, out):
        self.returncode = rc
        self.stdout = out
        self.stderr = ""


def test_its_008_a1_gitleaks_secret_finding_normalized(tmp_path, monkeypatch):
    findings_json = (
        '[{"File": "env.py", "StartLine": 3, "RuleID": "aws-access-token", '
        '"Description": "AWS Access Token detected"}]'
    )
    fake = _Gitleaks(findings_json)
    monkeypatch.setattr(subprocess, "run", fake)

    runner = SecurityScanRunner()
    report = runner.scan(str(tmp_path))

    assert fake.called
    assert len(report.secrets) == 1
    finding = report.secrets[0]
    assert finding.path == "env.py"
    assert finding.type == "secrets"
    assert finding.severity == Severity.HIGH
    assert report.partial is False and report.skipped is False


@pytest.mark.asyncio
async def test_its_008_a2_missing_gitleaks_skips_without_failing(tmp_path, monkeypatch):
    def not_found(argv, **kw):
        raise FileNotFoundError("gitleaks")

    monkeypatch.setattr(subprocess, "run", not_found)
    runner = SecurityScanRunner()
    report = runner.scan(str(tmp_path))
    assert report.skipped is True  # phase skipped, run continues (ARCH-008)


@pytest.mark.asyncio
async def test_its_008_a2b_llm_security_review_finds_pattern(tmp_path, monkeypatch):
    class FakeRunner:
        async def security_step(self, prompt):
            assert "=== TOOL FINDINGS ===" in prompt  # diff + tool findings wired in
            return ReviewResult(
                findings=[Finding(path="auth.py", severity=Severity.HIGH,
                                  title="Auth bypass", type="security")]
            )

    llm = LlmSecurityReviewer(FakeRunner())
    result = await llm.review(
        SecurityContext(diff="+if user.role == 'admin': pass", tool_findings=[])
    )
    assert len(result.findings) == 1
    assert result.findings[0].type == "security"
