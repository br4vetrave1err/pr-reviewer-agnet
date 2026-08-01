# Implements: ITP-013-A, ARCH-013, REQ-015, REQ-NF-001, REQ-NF-002, REQ-NF-003, REQ-NF-004
"""ITP-013-A: runtime signals, rate-limit backoff, and secret hygiene end-to-end."""

import asyncio
import json
import subprocess

import pytest

import httpx

from github.client import GitHubClient
from observability.log import RunLogger
from observability.ratelimit import backoff_delay
from queue.manager import QueueManager
from queue.worker import WorkerScheduler

from tests.integration.conftest import config, enqueue_decision, state


class FakeGate:
    def watch(self, job):
        pass


@pytest.mark.asyncio
async def test_its_013_a1_shutdown_drains_and_closes_db(state):
    gate = FakeGate()
    manager = QueueManager(state, gate)

    async def pipeline(job):
        await asyncio.sleep(0.001)
        return None

    worker = WorkerScheduler(manager, pipeline, max_attempts=3)
    task = asyncio.create_task(worker.run())

    run_id = manager.enqueue(enqueue_decision()).run_id
    state.set_status(run_id, "queued")

    await asyncio.sleep(0.05)
    task.cancel()  # SIGTERM equivalent: graceful drain
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert worker.active_workers == 0  # drained
    state.close()  # DB closes cleanly; no exit error


@pytest.mark.asyncio
async def test_its_013_a2_rate_limit_backoff_applied_and_recovers():
    class FlakyTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.calls = 0

        async def handle_async_request(self, request):
            self.calls += 1
            if self.calls < 3:
                return httpx.Response(429)  # rate limited twice, then succeeds
            return httpx.Response(200, json={"number": 1})

    sleeps = []
    original_sleep = asyncio.sleep

    async def fake_sleep(delay):
        sleeps.append(delay)
        await original_sleep(0)  # no real backoff wait in tests

    asyncio.sleep = fake_sleep
    try:
        client = GitHubClient(token="tok", base_url="https://api.github.com",
                              httpx_client=httpx.AsyncClient(transport=FlakyTransport()))
        data = await client.fetch_pr("acme", "app", 1)
    finally:
        asyncio.sleep = original_sleep

    assert len(sleeps) >= 2  # jittered exponential backoff applied (REQ-NF-003)
    assert data == {"number": 1}


def test_its_013_a3_no_secret_value_in_records(tmp_path):
    import io

    stream = io.StringIO()
    secret_value = "super-secret-pat-xyz"
    logger = RunLogger(runs_root=str(tmp_path / ".runs"), stream=stream, secrets=[secret_value])

    logger.log("run-1", "fetch", "info", token=secret_value, body="HEAD ok")
    logger.log("run-1", "submit", "info", summary="done")

    out = stream.getvalue()
    assert secret_value not in out  # value masked
    assert "[REDACTED]" in out  # key-name masked

    record = (tmp_path / ".runs" / "run-1" / "run.jsonl").read_text(encoding="utf-8")
    assert secret_value not in record  # persisted run record clean
    assert "[REDACTED]" in record


def test_its_013_a3b_deterministic_backoff_is_exponential():
    assert backoff_delay(1) == 10.0
    assert backoff_delay(2) == 20.0
    assert backoff_delay(3) == 40.0
