# Implements: ATP-002-A
"""ATP-002-A: author / requested-reviewer trigger conditions.

User journeys: opening a PR on an allowed repo enqueues a review; being added
as a requested reviewer enqueues one; events where the agent is neither
author nor reviewer are skipped with a logged reason.
"""

import logging

import pytest
from domain import NormalizedEvent

from tests.acceptance.conftest import pull_request_payload, wait_for


def _skipped_logs(caplog):
    return [r.getMessage() for r in caplog.records]


def test_scn_002_a1_open_pr_enqueues(journey):
    payload = pull_request_payload(action="opened", author="reviewer-bot")
    journey.deliver("pull_request", payload)

    wait_for(lambda: len(journey.state.reconcile_open_jobs()) >= 1)
    job = journey.state.reconcile_open_jobs()[0]
    assert job.owner == "acme" and job.repo == "app" and job.pr == 1


def test_scn_002_a2_requested_reviewer_enqueues(journey):
    import json

    body = json.loads(pull_request_payload(action="review_requested", author="someone-else").decode())
    body["pull_request"]["requested_reviewers"] = [{"login": "reviewer-bot"}]
    payload = json.dumps(body).encode()

    journey.deliver("pull_request", payload)
    wait_for(lambda: len(journey.state.reconcile_open_jobs()) >= 1)


def test_scn_002_a3_neither_author_nor_reviewer_skipped(journey, caplog):
    payload = pull_request_payload(action="opened", author="someone-else")
    journey.deliver("pull_request", payload)

    assert journey.state.reconcile_open_jobs() == []
    assert journey.github.posted == 0


def test_scn_002_a3_trigger_engine_skip_reason(caplog, config):
    from filter.trigger import TriggerDecisionEngine

    with caplog.at_level(logging.INFO):
        engine = TriggerDecisionEngine(config, "reviewer-bot")
        decision = engine.decide(
            NormalizedEvent(
                event="pull_request", action="opened", owner="acme", repo="app",
                pr_number=1, head_sha="abc123", author="someone-else",
                requested_reviewers=[], pr_state="open", sender="someone-else",
            )
        )
    assert decision.action == "skip"
    assert decision.reason == "not-self"
