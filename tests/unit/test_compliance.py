# Implements: UTP-010-A, UTS-010-A1, UTS-010-A2, UTS-010-A3, MOD-010, ARCH-007, REQ-008
"""Unit tests — MOD-010 (Test Compliance Validator)."""

from tests.compliance import ComplianceValidator, PrContext


def _validator(tmp_path):
    return ComplianceValidator(tmp_path)


def test_uts_010_a1_scope_violation_finding(tmp_path):
    ctx = PrContext(
        diff_files=["src/api.py", "src/unrelated/zzz.py"],
        title="Add billing API endpoint",
        body="Implements billing",
        issues=["Billing #12"],
    )
    findings = _validator(tmp_path).validate_scope(ctx)
    assert any(f.type == "scope" and f.path == "src/unrelated/zzz.py" for f in findings)


def test_uts_010_a1_scope_match_no_violation(tmp_path):
    ctx = PrContext(diff_files=["src/api.py"], title="Add billing API endpoint", body="billing api", issues=[])
    findings = _validator(tmp_path).validate_scope(ctx)
    assert findings == []


def test_uts_010_a2_test_additions_violating_conventions(tmp_path):
    (tmp_path / "AGENTS.md").write_text("tests live under tests/ and are named test_*.py", encoding="utf-8")
    v = _validator(tmp_path)
    conventions = v._infer_conventions()
    assert conventions
    findings = v.validate_compliance(["helpers/check.py"], conventions)
    assert any(f.type == "compliance" for f in findings)


def test_uts_010_a2_compliant_test_name_ok(tmp_path):
    v = _validator(tmp_path)
    assert v.validate_compliance(["tests/test_helpers.py"], ["AGENTS.md: test_*.py"]) == []


def test_uts_010_a3_no_local_test_execution(tmp_path):
    (tmp_path / "AGENTS.md").write_text("run pytest locally", encoding="utf-8")
    v = _validator(tmp_path)
    report = v.validate(PrContext(diff_files=["src/api.py", "tests/test_api.py"]))
    # Discovery only — no test execution, just compliance metadata.
    assert report.added_test_files == ["tests/test_api.py"]
    assert "missing_coverage" in report.__dataclass_fields__
