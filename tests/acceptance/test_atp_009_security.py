# Implements: ATP-009-A
"""ATP-009-A: security analysis â€” gitleaks secrets scan + LLM security review.

User journeys: a hard-coded secret in the checkout is reported by the secrets
scan and appears in the review; the LLM security review of the changed files
is produced; no scans run on a red head (a diagnosis comment is posted
instead).
"""

import asyncio

from security.scanner import SecReport
from tests.acceptance.conftest import pull_request_payload
from domain import Finding, Severity


class _SecretsScanner:
    def should_scan(self, ci_status):
        return ci_status in (None, "success", "green")

    def scan(self, checkout):
        return SecReport(
            secrets=[
                Finding(path="src/secrets.py", line=1, severity=Severity.HIGH,
                        title="Potential secret detected", detail="AWS key", type="secrets")
            ]
        )


async def test_scn_009_a1_secrets_scan_finding_in_review(journey):
    journey.scanner = _SecretsScanner()
    journey.pipeline._scanner = journey.scanner

    await journey.deliver_async(pull_request_payload())
    await journey.run_until(lambda: len(journey.github.reviews) >= 1)

    inline = journey.github.reviews[0]["inline"]
    assert any("secret" in c.lower() for c in [i["body"] for i in inline])


async def test_scn_009_a2_llm_security_review_produced(journey):
    # The /code-review prompt embeds a security step; the LLM review produces
    # a security finding surfaced in the review.
    from domain import ReviewResult

    journey.runner.result = ReviewResult(
        summary="Review complete.",
        findings=[Finding(path="src/api.py", line=5, severity=Severity.HIGH,
                         title="Injection risk", type="security")],
    )

    await journey.deliver_async(pull_request_payload())
    await journey.run_until(lambda: len(journey.github.reviews) >= 1)

    inline = journey.github.reviews[0]["inline"]
    assert any("injection" in i["body"].lower() for i in inline)


async def test_scn_009_a3_no_scans_on_red_head(journey):
    from tests.acceptance.conftest import FakeGithub, FakeRunner
    from github.client import CheckRun

    failed = [CheckRun(name="t", status="completed", conclusion="failure", completed=True, failed=True)]
    journey.github = FakeGithub(check_runs=failed)
    journey.pipeline._github = journey.github
    journey.ci_gate._github = journey.github  # the gate must see the red head

    scanned = {"n": 0}

    def boom(checkout):
        scanned["n"] += 1
        raise AssertionError("scans must not run on red head")

    journey.scanner.scan = boom
    journey.pipeline._scanner = journey.scanner

    # CI-failed: gate posts a diagnosis comment; no review, no scans
    from domain import ReviewResult

    journey.runner.result = ReviewResult(retryable=False, summary="")

    await journey.deliver_async(pull_request_payload())
    await journey.wait_until(lambda: len(journey.github.comments) >= 1)

    assert journey.github.posted == 0  # no review
    assert scanned["n"] == 0  # gitleaks never invoked (REQ-009)
    assert any("CI" in c for c in journey.github.comments)
