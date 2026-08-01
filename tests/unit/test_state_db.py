# Implements: UTP-015-A, UTS-015-A1, UTS-015-A2, MOD-015, ARCH-011, REQ-IF-005, REQ-NF-005
"""Unit tests — MOD-015 (State Repository)."""

import time

import pytest

from queue.manager import ReviewJob
from state.db import StateRepository


@pytest.fixture()
def state(tmp_path):
    s = StateRepository(str(tmp_path / "s.db"))
    yield s
    s.close()


def _job(run_id="r1", head="sha"):
    return ReviewJob(run_id=run_id, owner="a", repo="r", pr=1, head=head)


def test_uts_015_a1_dedup_conflict_treated_as_duplicate(state):
    assert state.insert_run(_job()) is True
    assert state.insert_run(_job(run_id="r2")) is False  # same (owner, repo, pr, head, model)


def test_uts_015_a1_different_head_is_new(state):
    assert state.insert_run(_job()) is True
    assert state.insert_run(_job(run_id="r2", head="sha2")) is True


def test_uts_015_a2_expired_lease_recovered_to_queued(state):
    state.insert_run(_job())
    state.set_status("r1", "running")
    state._conn.execute("UPDATE review_runs SET updated_at=0 WHERE run_id='r1'")
    state._conn.commit()
    n = state.recover_orphans(lease_ttl_seconds=1)
    assert n == 1
    assert state.get_run("r1").status == "queued"


def test_uts_015_a2_recovery_runs_once(state):
    state.insert_run(_job())
    state.set_status("r1", "running")
    state._conn.execute("UPDATE review_runs SET updated_at=0 WHERE run_id='r1'")
    state._conn.commit()
    state.recover_orphans(lease_ttl_seconds=1)
    assert state.recover_orphans(lease_ttl_seconds=1) == 0  # exactly once


def test_wal_journal_mode(state):
    row = state._conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0].lower() == "wal"
