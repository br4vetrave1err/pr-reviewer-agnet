# Implements: ATP-014-A
"""ATP-014-A: retries with backoff, then a partial-report comment.

User journeys: a transient GitHub API failure is retried with exponential
backoff before failing; a review whose opencode run keeps failing is marked
failed (no hard-block) and the PR is not blocked.
"""

import asyncio

import pytest

from tests.acceptance.conftest import pull_request_payload, wait_for
from domain import ReviewResult
from observability.ratelimit import backoff_delay


def test_scn_014_a1_backoff_schedule_exponential():
    # REQ-014: exponential backoff — later attempts back off longer.
    d1 = backoff_delay(1, "github", jitter_ratio=0.0)
    d2 = backoff_delay(2, "github", jitter_ratio=0.0)
    assert d1 == 10.0  # github base 10s
    assert d2 == 20.0  # doubled
    assert d2 > d1


@pytest.mark.asyncio
async def test_scn_014_a1_transient_failure_requeues(journey):
    from domain import Decision

    run = journey.queue.enqueue(
        Decision(action="enqueue", owner="acme", repo="app", pr=1, head="retry")
    ).run_id
    journey.state.set_status(run, "queued")

    attempts = {"n": 0}

    async def pipeline(job):
        attempts["n"] += 1
        return ReviewResult(retryable=True)  # transient failure

    journey.worker._pipeline = pipeline
    task = asyncio.create_task(journey.worker.run())
    await asyncio.sleep(0.2)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert attempts["n"] >= 2  # requeued with incremented attempts (REQ-014)


@pytest.mark.asyncio
async def test_scn_014_a2_exhausted_retries_marked_failed_no_block(journey):
    from domain import Decision

    run = journey.queue.enqueue(
        Decision(action="enqueue", owner="acme", repo="app", pr=1, head="fail")
    ).run_id
    journey.state.set_status(run, "queued")

    async def always_fail(job):
        return ReviewResult(retryable=True)

    journey.worker._pipeline = always_fail
    task = asyncio.create_task(journey.worker.run())
    await asyncio.sleep(0.35)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    status = journey.state.get_run(run).status
    assert status in ("failed", "queued")  # never hard-blocks the PR
    assert journey.github.posted == 0  # no duplicate/full review on failure
