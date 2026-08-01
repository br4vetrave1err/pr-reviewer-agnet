# Implements: UTP-017-A, UTS-017-A1, UTS-017-A2, MOD-017, ARCH-013, REQ-015, REQ-NF-001
"""Unit tests — MOD-017 (Logger & Run Records)."""

import io
import json

from observability.log import RunLogger


def test_uts_017_a1_run_record_contains_fields(tmp_path):
    stream = io.StringIO()
    logger = RunLogger(runs_root=tmp_path, stream=stream)
    logger.log("run1", "publish", "info", trigger="webhook", head="sha", model="free", outcome="posted")

    record = json.loads((tmp_path / "run1" / "run.jsonl").read_text(encoding="utf-8"))
    assert record["runId"] == "run1"
    assert record["trigger"] == "webhook"
    assert record["head"] == "sha"
    assert record["model"] == "free"
    assert record["outcome"] == "posted"


def test_uts_017_a2_secret_redacted_from_output(tmp_path):
    stream = io.StringIO()
    logger = RunLogger(runs_root=tmp_path, stream=stream, secrets=["supersecretvalue"])
    logger.log("run2", "workspace", "info", token="supersecretvalue")
    out = stream.getvalue()
    assert "supersecretvalue" not in out
    assert "[REDACTED]" in out


def test_uts_017_a2_secret_key_name_redacted(tmp_path):
    stream = io.StringIO()
    logger = RunLogger(runs_root=tmp_path, stream=stream)
    logger.log("run3", "workspace", "info", api_key="AKIAEXAMPLE")
    out = stream.getvalue()
    assert "AKIAEXAMPLE" not in out
    assert "[REDACTED]" in out
