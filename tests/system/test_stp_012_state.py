# Implements: STP-012-A, SYS-012, REQ-IF-005, REQ-NF-005
"""STP-012-A: SQLite transactional dedup and orphan recovery."""

import time

import pytest

from queue.manager import ReviewJob

from tests.system.conftest import state


def test_sts_012_a1_dedup_insert_ignored_as_duplicate(state):
    job = ReviewJob(owner="acme", repo="app", pr=1, head="abc123", model="free")
    assert state.insert_run(job) is True
    dup = ReviewJob(owner="acme", repo="app", pr=1, head="abc123", model="free")
    assert state.insert_run(dup) is False  # 0 rows affected (REQ-NF-005)
    assert len(state.reconcile_open_jobs()) == 1


def test_sts_012_a2_orphan_runs_requeued_no_double_post(state):
    job = ReviewJob(owner="acme", repo="app", pr=1, head="abc123", model="free")
    run_id = job.run_id
    state.insert_run(job)
    state.set_status(run_id, "running")

    # simulate a crash: backdate the running row beyond the lease TTL
    state._conn.execute(
        "UPDATE review_runs SET updated_at=? WHERE run_id=?",
        (int(time.time()) - 7200, run_id),
    )
    state._conn.commit()

    requeued = state.recover_orphans(lease_ttl_seconds=3600)
    assert requeued == 1
    assert state.get_run(run_id).status == "queued"  # ARCH-011
