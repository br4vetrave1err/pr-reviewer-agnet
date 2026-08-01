# Implements: ATP-IF-004-A, ATP-IF-005-A
"""ATP-IF-004 / ATP-IF-005: YAML config contract (fail-closed) and the SQLite
schema contract.

User journeys: a valid config.yaml boots with the configured providers,
repo_config, and defaults; an invalid config.yaml refuses to boot with a clear
error; a fresh database exposes review_runs, repos, model_aliases, repo_config
with the documented unique constraints.
"""

import json

import pytest
from config.load import ConfigError, load_config, validate
from tests.acceptance.conftest import ACCEPTANCE_CONFIG_RAW


def test_scn_if_004_a1_valid_config_boots(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        """
providers:
  free: { provider: opencode, model: o3-mini, enabled: true }
  go: { provider: opencode-go, model: gpt-5, enabled: true, auth_env: OPENCODE_GO_TOKEN }
default_model: free
repo_config:
  - owner: acme
    repo: app
""".lstrip(),
        encoding="utf-8",
    )
    cfg = load_config(p)

    assert cfg.default_model == "free"
    assert cfg.is_managed("acme", "app")
    assert set(cfg.providers) == {"free", "go"}


def test_scn_if_004_a2_invalid_config_refuses_to_boot(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("providers: []\n", encoding="utf-8")  # providers not a mapping
    with pytest.raises(ConfigError) as exc:
        load_config(p)
    assert "providers" in str(exc.value)


def test_scn_if_004_a2_missing_default_model_refuses(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        """
providers:
  free: { provider: opencode, model: o3-mini, enabled: true }
default_model: missing-alias
repo_config:
  - owner: acme
    repo: app
""".lstrip(),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as exc:
        load_config(p)
    assert "default_model" in str(exc.value)  # REQ-016 fail-closed


def test_scn_if_004_a2_webhook_secret_min_length():
    raw = json.loads(json.dumps(ACCEPTANCE_CONFIG_RAW))
    raw["webhook_secret"] = "short"
    with pytest.raises(ConfigError):
        validate(raw)


def test_scn_if_005_a1_schema_exposed(state):
    tables = {
        r[0] for r in state._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"review_runs", "repos", "model_aliases", "repo_config"} <= tables

    # documented unique constraints (REQ-IF-005)
    uniques = state._conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='review_runs'"
    ).fetchone()[0]
    assert "UNIQUE (owner, repo, pr, head, model)" in uniques
