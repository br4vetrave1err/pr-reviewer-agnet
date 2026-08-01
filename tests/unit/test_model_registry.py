# Implements: UTP-014-A, UTS-014-A1, UTS-014-A2, UTS-014-A3, UTP-014-B, UTS-014-B1, UTS-014-B2, MOD-014, ARCH-010, REQ-013, REQ-016
"""Unit tests — MOD-014 (Model Resolver)."""

import pytest

from config.load import validate
from models.registry import ModelRegistry, UnknownAliasError


def _config():
    raw = {
        "providers": {
            "free": {"provider": "opencode", "model": "o3-mini", "enabled": True},
            "go": {"provider": "opencode-go", "model": "gpt-5", "enabled": True, "auth_env": "OPENCODE_GO_TOKEN"},
        },
        "default_model": "free",
        "repo_config": [{"owner": "a", "repo": "r"}],
    }
    return validate(raw)


def test_uts_014_a1_configured_alias_resolves():
    registry = ModelRegistry(_config())
    m = registry.resolve("go")
    assert m.provider == "opencode-go"
    assert m.model == "gpt-5"
    assert m.auth_ref == "OPENCODE_GO_TOKEN"


def test_uts_014_a2_unknown_alias_raises_with_valid_list():
    registry = ModelRegistry(_config())
    with pytest.raises(UnknownAliasError) as exc:
        registry.resolve("nope")
    assert "free" in exc.value.valid_aliases


def test_uts_014_a3_default_alias_used_when_none():
    registry = ModelRegistry(_config())
    m = registry.resolve(None)
    assert m.alias == "free"


def test_uts_014_b1_switch_default_then_resolve():
    registry = ModelRegistry(_config())
    registry.switch_default("go")
    assert registry.resolve(None).alias == "go"


def test_uts_014_b2_switch_to_unknown_keeps_prior_default():
    registry = ModelRegistry(_config())
    with pytest.raises(UnknownAliasError):
        registry.switch_default("bogus")
    assert registry.resolve(None).alias == "free"
