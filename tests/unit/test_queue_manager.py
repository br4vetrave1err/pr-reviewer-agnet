# Implements: UTP-004-A, UTS-004-A1, UTS-004-A2, UTS-004-A3, MOD-004, ARCH-003, REQ-004, REQ-NF-005
"""Unit tests — MOD-004 (Queue Manager)."""

import pytest

from domain import Decision
from queue.manager import QueueManager
from state.db import StateRepository


@pytest.fixture()
def state(tmp_path):
    s = StateRepository(str(tmp_path / "test.db"))
    yield s
    s.close()


@pytest.fixture()
def manager(state):
    class FakeCiGate:
        def watch(self, job):
            pass

    return QueueManager(state, FakeCiGate(), max_attempts=3)


def _decision(owner="acme", repo="app", pr=1, head="sha1"):
    return Decision(action="enqueue", owner=owner, repo=repo, pr=pr, head=head)


def test_uts_004_a1_fresh_key_creates_run(manager, state):
    res = manager.enqueue(_decision())
    assert res.duplicate is False
    run = state.get_run(res.run_id)
    assert run.status == "pending_ci"


def test_uts_004_a2_duplicate_key_coalesces(manager, state):
    res1 = manager.enqueue(_decision())
    res2 = manager.enqueue(_decision(head="sha1"))
    assert res1.duplicate is False
    assert res2.duplicate is True


def test_uts_004_a2_distinct_head_is_new_run(manager, state):
    manager.enqueue(_decision())
    res2 = manager.enqueue(_decision(head="sha2"))
    assert res2.duplicate is False


def test_uts_004_a3_expired_lease_reacquirable(manager, state):
    res = manager.enqueue(_decision())
    state.set_status(res.run_id, "queued")
    state._conn.execute("UPDATE review_runs SET updated_at=0 WHERE run_id=?", (res.run_id,))
    state._conn.commit()
    assert state.acquire_lease(res.run_id, lease_ttl_seconds=1) is True
