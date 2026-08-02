# Implements: UTP-018, REQ-018, MOD-002, ARCH-002, SYS-002
"""Unit tests for Self-Authored Draft PR Ingress Filtering (REQ-018)."""

from domain import NormalizedEvent
from filter.trigger import TriggerDecisionEngine
from config.load import Config, RepoSpec


def test_draft_pr_self_authored_enqueued():
    config = Config(repo_config=[RepoSpec(owner="br4vetrave1err", repo="developer-roadmap")])
    engine = TriggerDecisionEngine(config, self_account="br4vetrave1err")

    event = NormalizedEvent(
        event="pull_request",
        action="opened",
        owner="br4vetrave1err",
        repo="developer-roadmap",
        pr_number=1,
        head_sha="head123",
        author="br4vetrave1err",
        draft=True,
    )
    decision = engine.decide(event)
    assert decision.action == "enqueue"


def test_draft_pr_other_author_skipped():
    config = Config(repo_config=[RepoSpec(owner="br4vetrave1err", repo="developer-roadmap")])
    engine = TriggerDecisionEngine(config, self_account="br4vetrave1err")

    event = NormalizedEvent(
        event="pull_request",
        action="opened",
        owner="br4vetrave1err",
        repo="developer-roadmap",
        pr_number=2,
        head_sha="head456",
        author="other_user",
        draft=True,
    )
    decision = engine.decide(event)
    assert decision.action == "skip"
    assert decision.reason == "draft-not-self"
