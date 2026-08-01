# Implements: UTP-002-A, UTS-002-A1, UTS-002-A2, UTS-002-A3, UTS-002-A4, MOD-002, ARCH-002, REQ-002, REQ-003
"""Unit tests — MOD-002 (Trigger Decision Engine)."""

import pytest

from config.load import Config, RepoSpec, validate
from domain import NormalizedEvent
from filter.trigger import TriggerDecisionEngine

SELF = "reviewer-bot"


def _config() -> Config:
    raw = {
        "providers": {"free": {"provider": "opencode", "model": "m", "enabled": True}},
        "repo_config": [{"owner": "acme", "repo": "app", "enabled": True}],
        "denylist": ["acme/badrepo"],
    }
    return validate(raw)


def _event(action="opened", owner="acme", repo="app", author="someone", reviewers=None, pr_state="open"):
    return NormalizedEvent(
        event="pull_request", action=action, owner=owner, repo=repo, pr_number=3,
        head_sha="sha", author=author, requested_reviewers=reviewers or [], pr_state=pr_state,
    )


def test_uts_002_a1_self_author_enqueue():
    engine = TriggerDecisionEngine(_config(), SELF)
    d = engine.decide(_event(author=SELF))
    assert d.action == "enqueue"
    assert d.repo == "app"


def test_uts_002_a2_self_reviewer_enqueue():
    engine = TriggerDecisionEngine(_config(), SELF)
    d = engine.decide(_event(action="review_requested", reviewers=[SELF]))
    assert d.action == "enqueue"


def test_uts_002_a3_not_author_or_reviewer_skip():
    engine = TriggerDecisionEngine(_config(), SELF)
    d = engine.decide(_event())
    assert d.action == "skip"
    assert d.reason == "not-self"


def test_uts_002_a4_denied_repo_skip():
    engine = TriggerDecisionEngine(_config(), SELF)
    d = engine.decide(_event(repo="badrepo", author=SELF))
    assert d.action == "skip"


def test_not_managed_repo_skip():
    engine = TriggerDecisionEngine(_config(), SELF)
    d = engine.decide(_event(repo="other", author=SELF))
    assert d.action == "skip"
    assert d.reason == "not-managed"


def test_issue_comment_not_self_skips():
    engine = TriggerDecisionEngine(_config(), SELF)
    ev = NormalizedEvent(event="issue_comment", action="created", owner="acme", repo="app",
                         author="human", comment_body="@review")
    assert engine.decide(ev).reason == "not-self"
