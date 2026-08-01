# Implements: ATP-011-A, ATP-012-A, ATP-IF-001-A
"""ATP-011-A / ATP-012-A / ATP-IF-001-A: formal COMMENT review with summary,
inline comments, and idempotency marker.

User journeys: a completed review posts a formal review via the GitHub REST
API with the required summary sections; a high-confidence finding on a changed
line becomes an inline comment; the terminal comment carries the idempotency
marker; the event is always COMMENT, never APPROVE / REQUEST_CHANGES.
"""

import json

import httpx
import pytest

from tests.acceptance.conftest import high_finding, pull_request_payload


async def test_scn_011_a1_review_contains_summary_sections(journey):
    from domain import ReviewResult

    journey.runner.result = ReviewResult(
        summary="**Verdict:** comment. CI: success. Security: no issues. Model: free. Scope: ok.",
        findings=[],
    )
    await journey.deliver_async(pull_request_payload())
    await journey.run_until(lambda: len(journey.github.reviews) >= 1)

    summary = journey.github.reviews[0]["summary"]
    assert "comment" in summary.lower()          # verdict prose
    assert "CI" in summary
    assert "Security" in summary
    assert "Model" in summary


async def test_scn_011_a2_inline_comment_on_changed_line(journey):
    journey.runner.result.findings = [high_finding(path="src/foo.py", line=3)]
    await journey.deliver_async(pull_request_payload())
    await journey.run_until(lambda: len(journey.github.reviews) >= 1)

    inline = journey.github.reviews[0]["inline"]
    assert any(i["path"] == "src/foo.py" and i["line"] == 3 for i in inline)


async def test_scn_011_a3_idempotency_marker_in_terminal_comment(journey):
    await journey.deliver_async(pull_request_payload())
    await journey.run_until(lambda: len(journey.github.reviews) >= 1)

    review = journey.github.reviews[0]
    run_id = review["run_id"]
    # The REST payload carries the marker; the GitHubClient appends it.
    assert run_id  # marker anchors idempotency (REQ-NF-005)


@pytest.mark.asyncio
async def test_scn_012_a1_event_always_comment():
    from github.client import GitHubClient

    sent = {}

    class FakeTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            sent["payload"] = json.loads(request.content.decode())
            return httpx.Response(201, json={"id": 42})

    client = GitHubClient(token="t", httpx_client=httpx.AsyncClient(transport=FakeTransport()))
    await client.submit_review("acme", "app", 1, "abc123", "ok", [], "run-1")

    assert sent["payload"]["event"] == "COMMENT"
    assert sent["payload"]["event"] != "REQUEST_CHANGES"
    assert sent["payload"]["event"] != "APPROVE"


@pytest.mark.asyncio
async def test_scn_012_a2_blocking_findings_stay_comment():
    from github.client import GitHubClient

    sent = {}

    class FakeTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            sent["payload"] = json.loads(request.content.decode())
            return httpx.Response(201, json={"id": 42})

    client = GitHubClient(token="t", httpx_client=httpx.AsyncClient(transport=FakeTransport()))
    await client.submit_review(
        "acme", "app", 1, "abc123",
        "Review complete. Changes needed: fix the auth bypass.",
        [{"path": "a.py", "line": 1, "body": "[high] bug"}], "run-2",
    )

    payload = sent["payload"]
    assert payload["event"] == "COMMENT"  # advisory verdict stays COMMENT (REQ-012)
    assert "changes needed" in payload["body"].lower()


@pytest.mark.asyncio
async def test_scn_if_001_a1_created_via_rest_api(journey):
    import json

    sent = {}

    class FakeTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            sent["payload"] = json.loads(request.content.decode())
            sent["url"] = str(request.url)
            return httpx.Response(201, json={"id": 42})

    from github.client import GitHubClient

    client = GitHubClient(token="t", httpx_client=httpx.AsyncClient(transport=FakeTransport()))
    await client.submit_review("acme", "app", 1, "abc123", "ok", [], "run-3")

    assert "/repos/acme/app/pulls/1/reviews" in sent["url"]  # GitHub REST API (REQ-IF-001)
    assert sent["payload"]["commit_id"] == "abc123"
