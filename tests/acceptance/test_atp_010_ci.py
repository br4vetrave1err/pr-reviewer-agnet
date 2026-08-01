# Implements: ATP-010-A
"""ATP-010-A: Rule B CI gate — no-CI bypass, failure diagnosis, wait cap.

User journeys: a head with no configured CI proceeds after the settle window;
a head whose gating CI failed gets a diagnosis comment and no review; a head
whose CI never completes gets one skip comment at the wait cap.
"""

import asyncio

import pytest

from tests.acceptance.conftest import pull_request_payload, wait_for
from domain import Decision
from github.client import CheckRun


def _failed_check():
    return [CheckRun(name="ci", status="completed", conclusion="failure", completed=True, failed=True)]


@pytest.mark.asyncio
async def test_scn_010_a1_no_ci_bypass_after_settle(journey):
    from queue.manager import PENDING_CI, QUEUED

    run = journey.queue.enqueue(Decision(action="enqueue", owner="acme", repo="app", pr=1, head="noci")).run_id
    journey.state.set_status(run, PENDING_CI)

    await journey.ci_gate._watch(journey.state.get_run(run))

    assert journey.state.get_run(run).status == QUEUED  # no-CI bypass


@pytest.mark.asyncio
async def test_scn_010_a2_failed_ci_diagnosis_no_review(journey):
    journey.github.check_runs = _failed_check()
    journey.pipeline._github = journey.github

    run = journey.queue.enqueue(Decision(action="enqueue", owner="acme", repo="app", pr=1, head="red")).run_id
    journey.state.set_status(run, "pending_ci")

    await journey.ci_gate._watch(journey.state.get_run(run))

    assert journey.state.get_run(run).status == "ci-failed"  # REQ-010
    assert journey.github.posted == 0  # no review
    assert any("CI gate failed" in c for c in journey.github.comments)


@pytest.mark.asyncio
async def test_scn_010_a3_ci_wait_cap_skips_with_comment(journey):
    journey.github.check_runs = [CheckRun(name="ci", status="in_progress", conclusion=None, completed=False, failed=False)]

    run = journey.queue.enqueue(Decision(action="enqueue", owner="acme", repo="app", pr=1, head="never")).run_id
    journey.state.set_status(run, "pending_ci")

    journey.ci_gate._cap = 0  # force the wait-cap path
    await journey.ci_gate._watch(journey.state.get_run(run))

    assert journey.state.get_run(run).status == "skipped"
    assert any("CI hasn't completed" in c for c in journey.github.comments)
    assert journey.github.posted == 0
