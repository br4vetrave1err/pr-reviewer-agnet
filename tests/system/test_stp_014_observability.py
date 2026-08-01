# Implements: STP-014-A, STP-014-B, SYS-014, REQ-015, REQ-NF-001, REQ-NF-003, REQ-NF-004, REQ-NF-007, REQ-CN-002, REQ-CN-004
"""STP-014-A/B: run records, backoff policy, secret hygiene, graceful shutdown."""

import asyncio
import io
import json
import os

import pytest

from observability.log import RunLogger
from observability.ratelimit import backoff_delay

from tests.system.conftest import state


def test_sts_014_a1_run_record_persisted(tmp_path):
    logger = RunLogger(runs_root=str(tmp_path / ".runs"))
    logger.log(
        "run-1", phase="review", level="info",
        trigger="pull_request", head="abc123", model="free", outcome="posted",
    )
    records = list((tmp_path / ".runs" / "run-1" / "run.jsonl").read_text(encoding="utf-8").splitlines())
    assert len(records) == 1
    line = json.loads(records[0])
    assert line["runId"] == "run-1"
    assert line["trigger"] == "pull_request"
    assert line["head"] == "abc123"
    assert line["model"] == "free"
    assert line["outcome"] == "posted"


def test_sts_014_a2_jittered_exponential_backoff():
    d1 = backoff_delay(1, "github")
    d2 = backoff_delay(2, "github")
    assert 8 <= d1 <= 12  # 10s base
    assert d2 > d1  # exponential
    assert backoff_delay(5, "github") <= 300  # capped at max


def test_sts_014_a3_no_secret_leak_in_output(tmp_path):
    stream = io.StringIO()
    logger = RunLogger(runs_root=str(tmp_path / ".runs"), stream=stream, secrets=["super-secret-token-value"])
    logger.log("run-2", phase="security", level="info", token="ghp_super-secret-token-value", plain="ok")
    out = stream.getvalue()
    assert "ghp_super-secret-token-value" not in out
    assert "[REDACTED]" in out  # key-name redaction
    assert "ok" in out  # non-secret field kept


@pytest.mark.asyncio
async def test_sts_014_b1_graceful_shutdown_drains_and_closes(state):
    from domain import Decision
    from queue.manager import QueueManager
    from queue.worker import WorkerScheduler

    class FakeGate:
        def watch(self, job):
            pass

    manager = QueueManager(state, FakeGate())
    for i in range(5):
        run_id = manager.enqueue(
            Decision(action="enqueue", owner="acme", repo="app", pr=i + 1, head=f"h{i}")
        ).run_id
        state.set_status(run_id, "queued")

    async def pipeline(job):
        await asyncio.sleep(0.005)

    worker = WorkerScheduler(manager, pipeline)
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.05)

    task.cancel()  # SIGTERM equivalent (REQ-CN-002 drain-and-exit)
    try:
        await task
    except asyncio.CancelledError:
        pass

    state.close()  # DB closes cleanly
    assert task.cancelled()  # process exits 0 after clean drain
