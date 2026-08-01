# Implements: ITP-010-A, ARCH-010, REQ-013, REQ-016
"""ITP-010-A: model resolution wired to run records; failures fail the run."""

import logging

import pytest

from domain import Command, NormalizedEvent
from filter.command import parse_command
from models.registry import ModelRegistry, UnknownAliasError

from tests.integration.conftest import config, state


def test_its_010_a1_command_model_resolved_and_recorded(config, state):
    cmd = parse_command("@review --model go")
    assert cmd.model == "go"

    registry = ModelRegistry(config)
    resolved = registry.resolve(cmd.model)
    assert resolved.provider == "opencode-go" and resolved.model == "gpt-5"

    event = NormalizedEvent(
        event="issue_comment", action="created", owner="acme", repo="app",
        pr_number=1, head_sha="abc123", author="reviewer-bot",
        comment_body="@review --model go", sender="reviewer-bot",
    )
    from filter.trigger import TriggerDecisionEngine
    from queue.manager import QueueManager

    class FakeGate:
        def watch(self, job):
            pass

    manager = QueueManager(state, FakeGate())
    trigger = TriggerDecisionEngine(config, self_account="reviewer-bot")
    decision = trigger.decide(event)
    assert decision.model == "go"

    run_id = manager.enqueue(decision).run_id
    assert state.get_run(run_id).model == "go"  # resolved alias recorded in the run


def test_its_010_a2_unknown_alias_fails_before_execution(config):
    registry = ModelRegistry(config)
    with pytest.raises(UnknownAliasError) as exc_info:
        registry.resolve("nope")
    assert "nope" in str(exc_info.value)
    assert "go" in " ".join(exc_info.value.valid_aliases)


def test_its_010_a3_config_only_default_switch_takes_effect(config, caplog):
    registry = ModelRegistry(config)
    before = registry.resolve().alias
    assert before == "free"  # current default

    registry.switch_default("go")  # REQ-016: config-only switch, no code change
    with caplog.at_level(logging.INFO):
        after = registry.resolve().alias
    assert after == "go"
    assert config.default_model == "go"
