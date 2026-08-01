# Implements: STP-011-A, SYS-011, REQ-013
"""STP-011-A: comment command parsing and help reply for malformed syntax."""

import pytest

from domain import Command, NormalizedEvent
from filter.command import CommandSyntaxError, parse_command, usage
from filter.trigger import TriggerDecisionEngine

from tests.system.conftest import config


def test_sts_011_a1_review_command_with_model():
    cmd = parse_command("@review --model go")
    assert isinstance(cmd, Command)
    assert cmd.kind == "review"
    assert cmd.model == "go"


def test_sts_011_a2_malformed_syntax_help_reply_no_enqueue(config):
    body = "@review --bogus-flag"
    with pytest.raises(CommandSyntaxError):
        parse_command(body)

    # trigger turns malformed into a reply decision; nothing is enqueued
    engine = TriggerDecisionEngine(config, "reviewer-bot")
    event = NormalizedEvent(
        event="issue_comment", action="created", owner="acme", repo="app",
        pr_number=1, head_sha="abc123", author="reviewer-bot", comment_body=body,
    )
    decision = engine.decide(event)
    assert decision.action == "reply"
    assert decision.reason == "malformed-command"

    # help reply lists valid aliases and is posted instead of enqueueing a run
    reply = usage(config.providers.keys())
    assert "Usage: `@review [--model <alias>]`" in reply
    assert "go" in reply and "free" in reply
