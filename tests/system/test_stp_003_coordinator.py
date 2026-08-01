# Implements: STP-003-A, STP-003-B, SYS-003, REQ-004, REQ-012, REQ-014, REQ-NF-005, REQ-NF-006
"""STP-003-A/B: dedup, bounded concurrency, retry, and always-COMMENT verdict."""

import asyncio

import pytest
from domain import Decision, ReviewResult
from queue.manager import QueueManager
from queue.worker import WorkerScheduler

from tests.system.conftest import review_job, state


class FakeGate:
    def watch(self, job):
        pass


def _decision(head="abc123"):
    return Decision(action="enqueue", owner="acme", repo="app", pr=1, head=head)


def test_sts_003_a1_duplicate_key_coalesces(state):
    manager = QueueManager(state, FakeGate())
    first = manager.enqueue(_decision(head="abc123")).run_id
    dup = manager.enqueue(_decision(head="abc123"))
    assert dup.duplicate is True
    assert len(state.reconcile_open_jobs()) == 1


@pytest.mark.asyncio
async def test_sts_003_a2_concurrency_bound_exactly_one(state):
    manager = QueueManager(state, FakeGate())
    for i in range(10):
        run_id = manager.enqueue(_decision(head=f"h{i}")).run_id
        state.set_status(run_id, "queued")

    executing = 0
    peak = 0

    async def pipeline(job):
        nonlocal executing, peak
        executing += 1
        peak = max(peak, executing)
        await asyncio.sleep(0.01)
        executing -= 1
        return None

    worker = WorkerScheduler(manager, pipeline, max_attempts=3, concurrency=1)
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.4)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert peak == 1  # REQ-NF-006: exactly one run at a time
    assert worker.active_workers == 0


@pytest.mark.asyncio
async def test_sts_003_a3_transient_failure_requeues_with_backoff(state):
    manager = QueueManager(state, FakeGate())
    run_id = manager.enqueue(_decision(head="retry")).run_id
    state.set_status(run_id, "queued")

    attempts = {"n": 0}

    async def pipeline(job):
        attempts["n"] += 1
        return ReviewResult(retryable=True)  # transient failure

    worker = WorkerScheduler(manager, pipeline, max_attempts=3)
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.15)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert attempts["n"] >= 2  # requeued with incremented attempt count (REQ-014)


@pytest.mark.asyncio
async def test_sts_003_b1_blocking_findings_still_posts_comment():
    import json

    import httpx

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
        [{"path": "a.py", "line": 1, "body": "[high] bug"}],
        "run-1",
    )
    payload = sent["payload"]
    assert payload["event"] == "COMMENT"  # never REQUEST_CHANGES
    assert "changes needed" in payload["body"].lower()


@pytest.mark.asyncio
async def test_sts_003_b2_clean_pass_never_approves():
    import json

    import httpx

    from github.client import GitHubClient

    sent = {}

    class FakeTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            sent["payload"] = json.loads(request.content.decode())
            return httpx.Response(201, json={"id": 42})

    client = GitHubClient(token="t", httpx_client=httpx.AsyncClient(transport=FakeTransport()))
    await client.submit_review(
        "acme", "app", 1, "abc123",
        "Review complete. No blocking findings — the PR is ready.",
        [], "run-2",
    )
    payload = sent["payload"]
    assert payload["event"] == "COMMENT"  # never APPROVE
    assert payload["event"] != "APPROVE"
    assert "ready" in payload["body"].lower()
