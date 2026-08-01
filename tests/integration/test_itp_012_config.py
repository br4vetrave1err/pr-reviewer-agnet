# Implements: ITP-012-A, ARCH-012, REQ-IF-004, REQ-016, REQ-017, REQ-CN-001
"""ITP-012-A: config failure halts boot; no webhook or queue starts."""

import pytest

from config.load import ConfigError, load_config, validate

from tests.integration.conftest import VALID_CONFIG_RAW


def test_its_012_a1_invalid_config_aborts_boot(tmp_path):
    bad = tmp_path / "config.yaml"
    bad.write_text("providers:\n  - broken\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(str(bad))

    # fail-closed: an app built on this config must never start
    with pytest.raises(ConfigError):
        validate({"providers": {}, "repo_config": []})


def test_its_012_a2_bad_default_model_or_agent_skills_aborts():
    raw = dict(VALID_CONFIG_RAW)
    raw["default_model"] = "does-not-exist"  # REQ-016: must be a defined alias
    with pytest.raises(ConfigError):
        validate(raw)

    raw2 = dict(VALID_CONFIG_RAW)
    raw2["agent_skill_set"] = {"base": "/code-review", "situational": "not-a-list"}  # REQ-017
    with pytest.raises(ConfigError):
        validate(raw2)


def test_its_012_a2b_unknown_agent_skill_base_still_boots_but_flagged(config):
    # base skill is not validated against disk at boot; missing skills are
    # surfaced by the SkillSetSelector at run time (ARCH-006).
    from executor.skills import SkillSetSelector

    missing = SkillSetSelector().missing_from_disk(["/does-not-exist"], [])
    assert "/does-not-exist" in missing
