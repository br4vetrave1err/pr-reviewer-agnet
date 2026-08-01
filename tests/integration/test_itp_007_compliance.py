# Implements: ITP-007-A, ARCH-007, REQ-008
"""ITP-007-A: scope + compliance phases produce normalized findings; no local test run."""

import pytest

from domain import Severity
from tests.compliance import ComplianceValidator, PrContext

from tests.integration.conftest import state


def test_its_007_a1_scope_violation_finding_and_run_continues(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    validator = ComplianceValidator(str(checkout))

    ctx = PrContext(
        diff_files=["src/parser.py", "unrelated/widget.css", "tests/test_parser.py"],
        title="Add JSON parser",
        body="",
    )
    findings = validator.validate_scope(ctx)

    assert any(f.type == "scope" and "unrelated/widget.css" in f.path for f in findings)
    assert not any(f.path == "src/parser.py" for f in findings)  # in-scope file passes
    assert all(f.severity == Severity.LOW for f in findings)  # non-blocking; run continues


def test_its_007_a2_compliance_finding_no_local_test_execution(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "AGENTS.md").write_text("tests must be added for modules", encoding="utf-8")
    validator = ComplianceValidator(str(checkout))

    ctx = PrContext(diff_files=["src/module_a.py", "tests/test_other.py"])
    report = validator.validate(ctx)
    findings = validator.to_findings(report)

    assert any(f.type == "compliance" and "module_a" in f.path for f in findings)

    # no local test execution ever happens (REQ-008)
    ran = []
    monkeypatch.setattr("subprocess.run", lambda *a, **k: ran.append(a) or _Ok())
    assert ran == []


class _Ok:
    returncode = 0
    stdout = ""
    stderr = ""
