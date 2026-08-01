# Implements: UTP-016-A, UTS-016-A1, UTS-016-A2, UTS-016-A3, UTP-016-B, UTS-016-B1, UTS-016-B2, MOD-016, ARCH-012, REQ-IF-004, REQ-CN-001
"""Unit tests — MOD-016 (Config Validator)."""

import pytest

from config.load import ConfigError, validate

VALID = {
    "providers": {
        "free": {"provider": "opencode", "model": "o3-mini", "enabled": True},
        "go": {"provider": "opencode-go", "model": "gpt-5", "enabled": True, "auth_env": "OPENCODE_GO_TOKEN"},
    },
    "default_model": "free",
    "repo_config": [{"owner": "acme", "repo": "app"}],
    "agent_skill_set": {"base": "/code-review", "situational": ["/diagnosing-bugs"]},
}


def test_uts_016_a1_valid_config_defaults_applied():
    cfg = validate(dict(VALID))
    assert cfg.default_model == "free"
    assert cfg.concurrency == 1  # default
    assert cfg.ci_gate.settle_seconds == 75  # default
    assert cfg.is_managed("acme", "app") is True


def test_uts_016_a2_invalid_secret_length_raises():
    raw = dict(VALID)
    raw["webhook_secret"] = "short"
    with pytest.raises(ConfigError):
        validate(raw)


def test_uts_016_a3_missing_required_keys_raises():
    with pytest.raises(ConfigError):
        validate({})


def test_uts_016_b1_default_model_not_in_providers():
    raw = dict(VALID)
    raw["default_model"] = "nope"
    with pytest.raises(ConfigError) as exc:
        validate(raw)
    assert "default_model" in str(exc.value)


def test_uts_016_b2_agent_skill_set_exposed():
    cfg = validate(dict(VALID))
    assert cfg.agent_skill_set.base == "/code-review"
    assert "/diagnosing-bugs" in cfg.agent_skill_set.situational
