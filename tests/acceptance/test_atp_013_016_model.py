# Implements: ATP-013-A, ATP-016-A
"""ATP-013-A / ATP-016-A: model aliases, per-PR override, single definition.

User journeys: `@review --model go` selects the go provider and the review
states the model; no override uses the configured default; an unknown or
disabled alias produces a help reply and no run; switching default_model is a
config-only change that takes effect on the next resolve; a per-PR override
still beats the new default.
"""

import json

import pytest

from config.load import validate as validate_config
from domain import Command
from filter.command import CommandSyntaxError, parse_command
from models.registry import ModelRegistry, UnknownAliasError
from tests.acceptance.conftest import (
    ACCEPTANCE_CONFIG_RAW,
    comment_payload,
    pull_request_payload,
)


async def test_scn_013_a1_model_override_runs_with_go(journey):
    payload = comment_payload("@review --model go", pr=1)
    await journey.deliver_async(payload, event="issue_comment")

    await journey.run_until(lambda: len(journey.runner.calls) >= 1)
    assert journey.runner.calls[0].model_alias == "go"
    assert journey.registry.resolve("go").provider == "opencode-go"


async def test_scn_013_a2_no_override_uses_default(journey):
    await journey.deliver_async(pull_request_payload())

    await journey.run_until(lambda: len(journey.runner.calls) >= 1)
    assert journey.runner.calls[0].model_alias == "free"  # configured default


async def test_scn_013_a3_unknown_alias_help_reply_no_run(journey):
    payload = comment_payload("@review --model nope", pr=1)
    await journey.deliver_async(payload, event="issue_comment")

    await journey.wait_until(lambda: len(journey.reply_comments) >= 1)
    assert journey.reply_comments
    assert "Valid model aliases" in journey.reply_comments[0]
    assert journey.runner.calls == []  # no review ran


def test_scn_013_a3_disabled_alias_rejected(journey):
    with pytest.raises(UnknownAliasError):
        journey.registry.resolve("gemini")  # defined but disabled


async def test_scn_016_a1_single_default_model_used(journey):
    await journey.deliver_async(pull_request_payload())
    await journey.run_until(lambda: len(journey.runner.calls) >= 1)
    assert journey.runner.calls[0].model_alias == "free"


def test_scn_016_a2_config_only_switch_default(journey):
    # REQ-016: switching the active model is a config change, no code change.
    registry = journey.registry
    registry.switch_default("go")  # config-only switch (REQ-016)

    resolved = registry.resolve()  # no override
    assert resolved.alias == "go"
    assert resolved.provider == "opencode-go"


async def test_scn_016_a3_override_beats_new_default(journey):
    journey.registry.switch_default("go")

    payload = comment_payload("@review --model free", pr=1)  # explicit override
    await journey.deliver_async(payload, event="issue_comment")
    await journey.run_until(lambda: len(journey.runner.calls) >= 1)

    assert journey.runner.calls[0].model_alias == "free"  # override wins (REQ-016)


def test_command_parser_contract():
    assert parse_command("Hey, @review --model go please") == Command(kind="review", model="go")
    assert parse_command("no token here") is None
    try:
        parse_command("@review --bogus")
        raise AssertionError("expected CommandSyntaxError")
    except CommandSyntaxError:
        pass
