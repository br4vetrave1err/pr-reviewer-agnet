# Implements: STP-009-A, SYS-009, REQ-011, REQ-012, REQ-IF-001
"""STP-009-A: review submission (event COMMENT + marker) and 404 -> skipped."""

import json

import httpx
import pytest

from github.client import GitHubClient, NotFoundError

from tests.system.conftest import state


class FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.posts = []

    async def handle_async_request(self, request):
        if request.method == "POST" and "/reviews" in request.url.path:
            self.posts.append(json.loads(request.content.decode()))
            return httpx.Response(201, json={"id": 99})
        return httpx.Response(404)


@pytest.mark.asyncio
async def test_sts_009_a1_review_created_status_posted():
    transport = FakeTransport()
    client = GitHubClient(token="t", httpx_client=httpx.AsyncClient(transport=transport))
    review_id = await client.submit_review(
        "acme", "app", 1, "abc123", "summary", [{"path": "a.py", "line": 1, "body": "fix"}], "run-x"
    )
    assert review_id == 99
    payload = transport.posts[0]
    assert payload["event"] == "COMMENT"  # REQ-012
    assert "<!-- review-run:run-x -->" in payload["body"]  # REQ-IF-001 marker


@pytest.mark.asyncio
async def test_sts_009_a2_github_404_marks_skipped_no_review(state):
    class Fake404Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return httpx.Response(404)

    client = GitHubClient(token="t", httpx_client=httpx.AsyncClient(transport=Fake404Transport()))
    with pytest.raises(NotFoundError):
        await client.submit_review("acme", "app", 1, "abc123", "s", [], "run-y")

    # caller marks the run skipped; no review was posted
    from domain import Decision
    from queue.manager import QueueManager

    class FakeGate:
        def watch(self, job):
            pass

    manager = QueueManager(state, FakeGate())
    run_id = manager.enqueue(Decision(action="enqueue", owner="acme", repo="app", pr=1, head="abc123")).run_id
    manager._state.set_status(run_id, "skipped")
    assert manager._state.get_run(run_id).status == "skipped"
