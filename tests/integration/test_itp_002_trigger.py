# Implements: ITP-002-A, ARCH-002, REQ-002, REQ-003, REQ-013
"""ITP-002-A: trigger decisions and parsed commands produce durable queue entries."""

import pytest

from domain import Decision, NormalizedEvent
from filter.command import parse_command
from queue.manager import QueueManager
from state.db import StateRepository
from webhook.dispatcher import Dispatcher

from tests.integration.conftest import VALID_CONFIG_RAW, state


class FakeGate:
    def __init__(self):
        self.watched = []

    def watch(self, job):
        self.watched.append(job.run_id)


@pytest.mark.asyncio
async def test_its_002_a1_accepted_author_trigger_enqueues_with_head(state, config):
    gate = FakeGate()
    manager = QueueManager(state, gate)
    event = NormalizedEvent(
        event="pull_request", action="opened", owner="acme", repo="app",
        pr_number=1, head_sha="abc123", author="reviewer-bot",
        requested_reviewers=[], pr_state="open", sender="reviewer-bot",
    )
    dispatcher = Dispatcher(_trigger(config), manager)
    await dispatcher.dispatch(event)

    jobs = state.reconcile_open_jobs()
    assert len(jobs) == 1
    assert jobs[0].owner == "acme" and jobs[0].repo == "app" and jobs[0].pr == 1
    assert jobs[0].head == "abc123"  # PR head carried to the queue entry


@pytest.mark.asyncio
async def test_its_002_a2_denied_repo_and_malformed_command_emit_no_job(state, config):
    replies = []

    async def reply_post(decision: Decision):
        replies.append(decision)

    gate = FakeGate()
    manager = QueueManager(state, gate)
    dispatcher = Dispatcher(_trigger(config), manager, reply_post=reply_post)

    denied = NormalizedEvent(
        event="pull_request", action="opened", owner="evil", repo="app",
        pr_number=9, head_sha="x", author="reviewer-bot",
        requested_reviewers=[], pr_state="open", sender="reviewer-bot",
    )
    await dispatcher.dispatch(denied)

    malformed = NormalizedEvent(
        event="issue_comment", action="created", owner="acme", repo="app",
        pr_number=1, head_sha="abc123", author="reviewer-bot",
        comment_body="@review --bogus-flag", sender="reviewer-bot",
    )
    await dispatcher.dispatch(malformed)

    assert state.reconcile_open_jobs() == []  # no job enqueued
    assert len(replies) == 1  # help reply emitted for the malformed command


def test_its_002_a2_malformed_command_parses_as_syntax_error():
    with pytest.raises(Exception):
        parse_command("@review --model x --bad-flag y")


def _trigger(config):
    from filter.trigger import TriggerDecisionEngine

    return TriggerDecisionEngine(config, self_account="reviewer-bot")
