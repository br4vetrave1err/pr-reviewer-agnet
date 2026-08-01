# Implements: STP-013-A, SYS-013, REQ-IF-004, REQ-016, REQ-017, REQ-CN-001
"""STP-013-A: config load and fail-closed validation."""

import pytest

from config.load import ConfigError, validate as validate_config

from tests.system.conftest import SYSTEM_CONFIG_RAW


def test_sts_013_a1_valid_config_typed_with_defaults():
    config = validate_config(dict(SYSTEM_CONFIG_RAW))
    assert config.default_model == "free"
    assert config.concurrency == 1  # default applied
    assert config.agent_skill_set.base == "/code-review"
    assert config.retry.max_attempts == 3
    assert config.repo_config[0].owner == "acme"


def test_sts_013_a2_invalid_config_raises_config_error():
    with pytest.raises(ConfigError):
        validate_config({"providers": {}, "repo_config": []})


def test_sts_013_a3_single_model_definition_validated_and_fails_closed():
    # valid: default_model present in providers; skill set typed
    config = validate_config(dict(SYSTEM_CONFIG_RAW))
    assert config.providers["free"].model == "o3-mini"
    assert config.agent_skill_set.situational == ["/diagnosing-bugs", "/resolving-merge-conflicts"]

    # violating config fails closed (REQ-016 / REQ-017)
    bad = dict(SYSTEM_CONFIG_RAW)
    bad["default_model"] = "does-not-exist"
    with pytest.raises(ConfigError):
        validate_config(bad)

    bad2 = dict(SYSTEM_CONFIG_RAW)
    bad2["agent_skill_set"] = {"base": "/code-review", "situational": "not-a-list"}
    with pytest.raises(ConfigError):
        validate_config(bad2)
