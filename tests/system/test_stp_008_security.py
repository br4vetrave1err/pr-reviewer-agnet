# Implements: STP-008-A, SYS-008, REQ-009
"""STP-008-A: gitleaks scan, LLM security review, and tool-missing degradation."""

import json
import logging
import subprocess

import pytest

from security.llm import LlmSecurityReviewer, SecurityContext
from security.scanner import SecurityScanRunner


class _FakeProc:
    def __init__(self, rc=0, out=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = ""


def test_sts_008_a1_gitleaks_normalizes_secret_finding(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: _FakeProc(
            rc=1,  # 1 = findings present
            out=json.dumps([{"File": "src/auth.py", "StartLine": 42, "Description": "AWS secret key"}]),
        ),
    )
    report = SecurityScanRunner().scan(str(tmp_path))
    assert len(report.secrets) == 1
    assert report.secrets[0].type == "secrets"
    assert report.secrets[0].path == "src/auth.py"
    assert report.secrets[0].severity.value == "high"


@pytest.mark.asyncio
async def test_sts_008_a2_llm_security_review_inside_session(tmp_path, monkeypatch):
    from domain import Finding, ReviewResult, Severity

    class FakeRunner:
        async def security_step(self, prompt):
            assert "Security review step" in prompt
            return ReviewResult(
                summary="",
                findings=[Finding(path="src/api.py", severity=Severity.HIGH, title="Auth bypass", type="security")],
            )

    reviewer = LlmSecurityReviewer(FakeRunner())
    result = await reviewer.review(SecurityContext(diff="diff", tool_findings=[]))
    assert any(f.type == "security" for f in result.findings)


@pytest.mark.asyncio
async def test_sts_008_a3_tool_missing_skips_and_logs(tmp_path, monkeypatch, caplog):
    def boom(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", boom)
    with caplog.at_level(logging.WARNING):
        report = SecurityScanRunner().scan(str(tmp_path))
    assert report.skipped is True
    assert report.secrets == []  # run continues, no findings
    assert any("gitleaks not found" in r.message for r in caplog.records)
