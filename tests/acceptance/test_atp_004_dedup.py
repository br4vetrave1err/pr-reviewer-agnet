# Implements: ATP-004-A
"""ATP-004-A: dedup and re-review on new head.

User journeys: an identical event for an already-reviewed head+model posts no
duplicate; a synchronize event with a new head SHA produces a fresh review.
"""

import pytest

from tests.acceptance.conftest import pull_request_payload


@pytest.mark.asyncio
async def test_scn_004_a1_no_duplicate_review_for_same_head(journey):
    await journey.deliver_async(pull_request_payload(action="opened", head="abc123"))
    await journey.run_until(lambda: len(journey.github.reviews) >= 1)
    assert len(journey.github.reviews) == 1

    # identical event arrives again
    await journey.deliver_async(pull_request_payload(action="synchronize", head="abc123"))
    assert len(journey.state.reconcile_open_jobs()) <= 1  # coalesced by dedup

    # second identical event must not post a second review
    await journey.deliver_async(pull_request_payload(action="synchronize", head="abc123"))
    await journey.wait_until(lambda: journey.github.posted == 1)
    assert journey.github.posted == 1


@pytest.mark.asyncio
async def test_scn_004_a2_new_head_produces_fresh_review(journey):
    # First review posted for SHA-A
    await journey.deliver_async(pull_request_payload(action="opened", head="sha-a"))
    await journey.run_until(lambda: len(journey.github.reviews) >= 1)
    assert journey.github.posted == 1

    # synchronize to SHA-B -> distinct run key -> fresh review
    await journey.deliver_async(pull_request_payload(action="synchronize", head="sha-b"))
    await journey.run_until(lambda: journey.github.posted >= 2)
    assert journey.github.posted == 2


async def test_scn_004_a1_transactional_dedup_key(journey):
    from queue.manager import ReviewJob

    job = ReviewJob(owner="acme", repo="app", pr=1, head="dup", model="free")
    inserted = journey.state.insert_run(job)
    second = ReviewJob(owner="acme", repo="app", pr=1, head="dup", model="free")
    assert journey.state.insert_run(second) is False  # UNIQUE(owner,repo,pr,head,model)
