# Implements: ATP-015-A, ATP-NF-007-A, ATP-NF-004-A
"""ATP-015-A / ATP-NF-007-A / ATP-NF-004-A: run records, structured JSON logs,
and secret hygiene.

User journeys: every run persists a structured record (trigger, inputs, head
SHA, model, outcome, timestamps); logs are structured JSON carrying trigger,
repo, PR, head, model, phases, outcome; secret values never appear in logs or
review output.
"""

import io
import json

import pytest

from observability.log import RunLogger
from tests.acceptance.conftest import pull_request_payload, wait_for


@pytest.mark.asyncio
async def test_scn_015_a1_run_record_persisted(journey):
    from domain import Decision

    run = journey.queue.enqueue(
        Decision(action="enqueue", owner="acme", repo="app", pr=1, head="sha1", model="free")
    ).run_id
    journey.state.set_status(run, "posted")

    assert journey.state.get_run(run).owner == "acme"
    assert journey.state.get_run(run).head == "sha1"
    assert journey.state.get_run(run).model == "free"
    assert journey.state.get_run(run).status == "posted"


def test_scn_nf_007_a1_json_log_lines_with_run_fields():
    stream = io.StringIO()
    logger = RunLogger(runs_root="/tmp/no-runs", stream=stream)
    logger.log("run-9", "publish", "info", trigger="webhook", repo="app", pr=1,
               head="abc123", model="free", outcome="posted")

    line = json.loads(stream.getvalue().strip())
    assert line["runId"] == "run-9"
    assert line["trigger"] == "webhook"
    assert line["repo"] == "app"
    assert line["pr"] == 1
    assert line["head"] == "abc123"
    assert line["model"] == "free"
    assert line["phase"] == "publish"
    assert line["outcome"] == "posted"


def test_scn_nf_004_a1_secrets_never_in_logs():
    stream = io.StringIO()
    logger = RunLogger(runs_root="/tmp/no-runs", stream=stream,
                       secrets=["sk-super-secret-token"])
    logger.log("run-9", "github", "info", token="sk-super-secret-token")

    text = stream.getvalue()
    assert "sk-super-secret-token" not in text  # REQ-NF-004
    assert "[REDACTED]" in text


def test_scn_nf_004_a1_config_has_no_key_material():
    from config.load import load_config
    from tests.acceptance.conftest import ACCEPTANCE_CONFIG_RAW
    import tempfile, os

    raw = json.loads(json.dumps(ACCEPTANCE_CONFIG_RAW))
    # secrets only referenced by env-var NAME (auth_env), never by value
    for alias, spec in raw["providers"].items():
        assert "token" not in str(spec.get("auth_env", "")).lower() or spec["auth_env"] == "OPENCODE_GO_TOKEN"
        assert "sk-" not in str(spec)
