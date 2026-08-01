# Implements: STP-002-A, SYS-002, REQ-002, REQ-003
"""STP-002-A: trigger + managed-repo decision matrix (author/reviewer/other × managed/denied)."""

import pytest

from domain import NormalizedEvent
from filter.trigger import TriggerDecisionEngine

from tests.system.conftest import config


def _event(author="reviewer-bot", action="opened", owner="acme", repo="app", requested=None):
    return NormalizedEvent(
        event="pull_request", action=action, owner=owner, repo=repo,
        pr_number=1, head_sha="abc123", author=author,
        requested_reviewers=requested or [], pr_state="open", sender=author,
    )


def test_sts_002_a1_self_author_managed_repo_enqueues(config):
    decision = TriggerDecisionEngine(config, "reviewer-bot").decide(
        _event(author="reviewer-bot")
    )
    assert decision.action == "enqueue"
    assert decision.head == "abc123"


def test_sts_002_a2_not_self_skips_not_self(config):
    decision = TriggerDecisionEngine(config, "reviewer-bot").decide(
        _event(author="some-human")
    )
    assert decision.action == "skip"
    assert decision.reason == "not-self"


def test_sts_002_a3_unmanaged_or_denied_repo_skips(config):
    engine = TriggerDecisionEngine(config, "reviewer-bot")
    decision = engine.decide(_event(author="reviewer-bot", owner="othercorp", repo="unmanaged"))
    assert decision.action == "skip"
    assert decision.reason == "not-managed"  # REQ-003


def test_sts_002_a3b_reviewer_request_managed_enqueues(config):
    decision = TriggerDecisionEngine(config, "reviewer-bot").decide(
        _event(author="someone", action="review_requested", requested=["reviewer-bot"])
    )
    assert decision.action == "enqueue"
