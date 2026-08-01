# Implements: ITP-011-A, ARCH-011, REQ-IF-005, REQ-NF-005
"""ITP-011-A: state store recovers orphaned/in-flight runs on boot."""

import time

import pytest

from queue.manager import QueueManager

from tests.integration.conftest import enqueue_decision, state


class FakeGate:
    def watch(self, job):
        pass


def test_its_011_a1_orphaned_running_rows_requeued_no_double_post(state):
    manager = QueueManager(state, FakeGate())
    run_id = manager.enqueue(enqueue_decision(head="oldsha")).run_id

    state.set_status(run_id, "running")
    old_ts = time.time() - 7200  # simulate a crash that left it running past the TTL
    state._conn.execute("UPDATE review_runs SET updated_at=? WHERE run_id=?", (int(old_ts), run_id))
    state._conn.commit()

    recovered = state.recover_orphans(lease_ttl_seconds=3600)
    assert recovered == 1

    jobs = state.reconcile_open_jobs()
    assert len(jobs) == 1 and jobs[0].status == "queued"  # requeued on boot (ARCH-011)
    assert jobs[0].run_id == run_id  # same run, no double-post


def test_its_011_a2_lease_expiry_makes_row_recoverable(state):
    manager = QueueManager(state, FakeGate())
    run_id = manager.enqueue(enqueue_decision(head="leasesha")).run_id
    state.set_status(run_id, "queued")

    old_ts = time.time() - 7200
    state._conn.execute("UPDATE review_runs SET updated_at=? WHERE run_id=?", (int(old_ts), run_id))
    state._conn.commit()

    assert state.acquire_lease(run_id, lease_ttl_seconds=3600) is True  # lease expired -> reacquired
    assert state.get_run(run_id).status == "running"  # processed exactly once

    assert state.acquire_lease(run_id, lease_ttl_seconds=3600) is False  # fresh lease blocks second claim
