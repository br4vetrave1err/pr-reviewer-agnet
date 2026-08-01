# Implements: UTP-009-A, UTS-009-A1, UTS-009-A2, UTS-009-A3, MOD-009, ARCH-006, REQ-010
"""Unit tests — MOD-009 (CI Gate Monitor)."""

import pytest

from ci.gate import CiGateMonitor
from github.client import CheckRun


class FakeGithub:
    def __init__(self, runs):
        self._runs = runs

    async def poll_check_runs(self, owner, repo, head):
        return self._runs


class FakeState:
    def get_run(self, run_id):
        return None


@pytest.mark.asyncio
async def test_uts_009_a1_no_ci_bypass_after_settle():
    gate = CiGateMonitor(FakeGithub([]), FakeState(), settle_seconds=75, wait_cap_minutes=60)
    res = await gate.resolve_gate("head", elapsed_seconds=90)
    assert res.passed is True
    assert res.reason == "no-ci"


@pytest.mark.asyncio
async def test_uts_009_a1_no_ci_before_settle_pending():
    gate = CiGateMonitor(FakeGithub([]), FakeState(), settle_seconds=75, wait_cap_minutes=60)
    res = await gate.resolve_gate("head", elapsed_seconds=10)
    assert res.passed is False
    assert res.reason == "pending"


@pytest.mark.asyncio
async def test_uts_009_a2_failed_ci_blocks_gate():
    gate = CiGateMonitor(
        FakeGithub([CheckRun(name="build", status="completed", conclusion="failure", completed=True, failed=True)]),
        FakeState(),
    )
    res = await gate.resolve_gate("head", elapsed_seconds=10)
    assert res.passed is False
    assert res.reason == "ci-failed"


@pytest.mark.asyncio
async def test_uts_009_a2_green_ci_passes():
    gate = CiGateMonitor(
        FakeGithub([CheckRun(name="build", status="completed", conclusion="success", completed=True, failed=False)]),
        FakeState(),
    )
    res = await gate.resolve_gate("head", elapsed_seconds=10)
    assert res.passed is True
    assert res.reason == "green"


@pytest.mark.asyncio
async def test_uts_009_a3_pending_ci_times_out():
    gate = CiGateMonitor(
        FakeGithub([CheckRun(name="build", status="in_progress", conclusion=None, completed=False, failed=False)]),
        FakeState(),
        wait_cap_minutes=60,
    )
    res = await gate.resolve_gate("head", elapsed_seconds=3601)
    assert res.passed is False
    assert res.reason == "timeout"
