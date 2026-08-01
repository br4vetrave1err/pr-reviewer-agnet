# Implements: UTP-005-A, UTS-005-A1, UTS-005-A2, MOD-005, ARCH-003, REQ-004, REQ-NF-006, REQ-014
"""Unit tests — MOD-005 (Worker Scheduler)."""

import asyncio

import pytest

from domain import Decision
from queue.manager import QueueManager
from queue.worker import WorkerScheduler
from state.db import StateRepository


class FakeResult:
    def __init__(self, retryable=False, status="posted"):
        self.retryable = retryable
        self.status = status


class FakeCiGate:
    def watch(self, job):
        job.status = "queued"  # simulate green/no-CI bypass to queued


@pytest.fixture()
def state(tmp_path):
    s = StateRepository(str(tmp_path / "w.db"))
    yield s
    s.close()


@pytest.fixture()
def manager(state):
    return QueueManager(state, FakeCiGate(), max_attempts=3)


def test_uts_005_a1_concurrency_bound(manager):
    decisions = [Decision(action="enqueue", owner="a", repo="r", pr=i, head=f"s{i}") for i in range(10)]
    for d in decisions:
        res = manager.enqueue(d)
        manager._state.set_status(res.run_id, "queued")  # simulate CI gate bypass

    active_seen = []
    processed = []

    async def pipeline(job):
        active_seen.append(worker.active_workers)
        processed.append(job.run_id)
        await asyncio.sleep(0.02)  # hold the worker slot so overlap is observable
        return FakeResult()

    async def scenario():
        nonlocal worker
        worker = WorkerScheduler(manager, pipeline, concurrency=2, idle_backoff_seconds=0.005)
        task = asyncio.create_task(worker.run())
        for _ in range(200):
            if len(processed) >= 10:
                break
            await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    worker = None
    asyncio.run(scenario())
    assert len(processed) == 10
    assert max(active_seen) <= 2  # concurrency bound respected
    assert max(active_seen) >= 2  # two workers genuinely overlapped


def test_uts_005_a2_transient_failure_retries_up_to_max(manager):
    res = manager.enqueue(Decision(action="enqueue", owner="a", repo="r", pr=1, head="s"))
    manager._state.set_status(res.run_id, "queued")  # simulate CI gate bypass
    run_id = res.run_id
    attempts = {"n": 0}

    async def pipeline(job):
        attempts["n"] += 1
        return FakeResult(retryable=True)

    async def scenario():
        worker = WorkerScheduler(manager, pipeline, max_attempts=3, concurrency=1, idle_backoff_seconds=0.005)
        task = asyncio.create_task(worker.run())
        for _ in range(300):
            run = manager._state.get_run(run_id)
            if run.status in ("failed", "posted"):
                break
            await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())
    run = manager._state.get_run(run_id)
    assert attempts["n"] >= 4  # initial + retries up to max
    assert run.status == "failed"
