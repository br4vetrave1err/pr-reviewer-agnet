# Implements: UTP-011-A, UTS-011-A1, UTS-011-A2, UTS-011-A3, MOD-011, ARCH-008, REQ-009
"""Unit tests — MOD-011 (Security Scan Runner)."""

import json
import subprocess

import pytest

from security.scanner import SecurityScanRunner


def test_uts_011_a1_full_checkout_secrets_normalized(tmp_path, monkeypatch):
    report = [{"File": "a.py", "StartLine": 5, "Description": "AWS key"}]
    stdout = json.dumps(report)

    def fake_run(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = SecurityScanRunner()
    sec = runner.scan(str(tmp_path))
    assert sec.skipped is False
    assert sec.secrets[0].path == "a.py"
    assert sec.secrets[0].type == "secrets"
    assert sec.secrets[0].severity.value == "high"


def test_uts_011_a2_no_scan_on_red_head():
    runner = SecurityScanRunner()
    assert runner.should_scan("failure") is False
    assert runner.should_scan("success") is True


def test_uts_011_a3_missing_binary_skips_without_raise(tmp_path, monkeypatch):
    def fake_run(argv, **kw):
        raise FileNotFoundError("gitleaks")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = SecurityScanRunner()
    sec = runner.scan(str(tmp_path))
    assert sec.skipped is True
    assert sec.secrets == []
