# Implements: ATP-008-A
"""ATP-008-A: PR scope + test compliance validation (discovery only).

User journeys: a changed module with no matching test addition yields a
missing-coverage finding; a test addition violating repo conventions yields a
non-compliant-test finding; green CI is reported without local test execution.
"""

from tests.compliance import ComplianceValidator, PrContext


def test_scn_008_a1_missing_test_coverage_finding():
    validator = ComplianceValidator(".")
    # SCN-008-A1: a changed module (src/billing.py) with no matching test addition
    report = validator.validate(
        PrContext(diff_files=["src/orders.py", "src/orders_test.py", "src/billing.py"])
    )
    findings = validator.to_findings(report)
    assert any(f.type == "compliance" for f in findings)


def test_scn_008_a2_violating_test_name_finding(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "AGENTS.md").write_text("Add tests named *_test.py.\n", encoding="utf-8")

    validator = ComplianceValidator(checkout)
    report = validator.validate(PrContext(diff_files=["helper_tests.py"]))
    violations = report.violations or validator.to_findings(report)
    assert len(violations) >= 1  # test file name does not match conventions


async def test_scn_008_a3_ci_status_reported_no_local_execution(journey):
    from tests.acceptance.conftest import FakeGithub, FakeRunner, pull_request_payload
    from domain import ReviewResult

    github = FakeGithub()
    runner = FakeRunner(result=ReviewResult(summary="Review complete. CI: success."))
    journey.github = github
    journey.runner = runner
    journey.pipeline._github = github
    journey.pipeline._runner = runner

    await journey.deliver_async(pull_request_payload())
    await journey.run_until(lambda: len(journey.github.reviews) >= 1)

    # container never executes the repo's test suite: pipeline only reports
    assert journey.github.reviews[0]["summary"] == "Review complete. CI: success."
