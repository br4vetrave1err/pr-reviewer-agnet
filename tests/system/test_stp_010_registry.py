# Implements: STP-010-A, SYS-010, REQ-013, REQ-016
"""STP-010-A: alias resolution, unknown alias, and default-model switch precedence."""

import pytest

from models.registry import ModelRegistry, UnknownAliasError

from tests.system.conftest import config


def test_sts_010_a1_resolve_configured_alias(config):
    resolved = ModelRegistry(config).resolve("go")
    assert resolved.alias == "go"
    assert resolved.provider == "opencode-go"
    assert resolved.model == "gpt-5"
    assert resolved.auth_ref == "OPENCODE_GO_TOKEN"


def test_sts_010_a2_unknown_alias_raises_with_valid_list(config):
    with pytest.raises(UnknownAliasError) as exc:
        ModelRegistry(config).resolve("nope")
    assert "nope" in str(exc.value)
    assert "free" in str(exc.value)  # valid aliases listed
    assert "go" in str(exc.value)


def test_sts_010_a3_default_switch_effective_and_override_wins(config):
    registry = ModelRegistry(config)
    before = registry.resolve(None)
    assert before.alias == "free"  # configured default

    registry.switchDefault("go")  # config-only switch (REQ-016)
    after = registry.resolve(None)
    assert after.alias == "go"

    # per-PR @review --model <alias> override takes precedence over the default
    per_pr = registry.resolve("free")
    assert per_pr.alias == "free"
