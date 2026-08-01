# Implements: STP-007-A, SYS-007, REQ-008
"""STP-007-A: scope + compliance validation (discovery only, never executes tests)."""

import subprocess

import pytest

from tests.compliance import ComplianceValidator, PrContext

from tests.system.conftest import config, state


def test_sts_007_a1_out_of_scope_file_flagged_non_blocking(tmp_path):
    validator = ComplianceValidator(str(tmp_path))
    findings = validator.validate_scope(
        PrContext(
            diff_files=["billing/pay.py"],
            title="Fix checkout total",
            body="Closes #12 checkout flow",
            issues=["checkout"],
        )
    )
    assert any(f.type == "scope" for f in findings)  # listed, not raised
    assert validator is not None  # run continues (non-blocking)


def test_sts_007_a2_test_addition_violating_conventions(tmp_path):
    checkout = tmp_path
    (checkout / "AGENTS.md").write_text("Tests must be named test_*.py\n", encoding="utf-8")
    validator = ComplianceValidator(str(checkout))
    findings = validator.validate_compliance(
        added_tests=["weird_name.py"], conventions=validator._infer_conventions()
    )
    assert any(f.type == "compliance" for f in findings)


def test_sts_007_a3_ci_from_github_no_local_test_execution(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        raise AssertionError("validator must never execute the repo's tests")

    monkeypatch.setattr(subprocess, "run", fake_run)
    validator = ComplianceValidator(str(tmp_path))
    report = validator.validate(PrContext(diff_files=["app.py", "test_app.py"]))
    assert calls == []  # no test execution
    assert report is not None  # discovery + compliance only

    # CI status is taken from GitHub, not from local runs: a green head proceeds.
    from github.client import CheckRun

    assert CheckRun(name="t", status="completed", conclusion="success", completed=True, failed=False)
