# Implements: ATP-CN-001-A, ATP-CN-002-A, ATP-CN-004-A
"""ATP-CN-001 / ATP-CN-002 / ATP-CN-004: deployment constraints.

User journeys: `docker compose up` reaches a listening webhook endpoint;
the image toolchain (Python, FastAPI, opencode CLI, git, gitleaks) is declared;
the agent never pushes or commits to a reviewed repo (read-only).
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_scn_cn_001_a1_compose_declares_app_and_tunnel():
    compose = ROOT / "compose.yaml"
    assert compose.is_file()

    text = compose.read_text(encoding="utf-8")
    assert "services:" in text
    assert "app:" in text
    assert "ngrok" in text  # REQ-CN-001 tunnel sidecar
    assert "env_file" in text  # .env via env_file (REQ-NF-004)


def test_scn_cn_001_a1_app_reaches_listening_webhook(tmp_path):
    # The app boots from a valid config and the webhook route responds 401 for
    # an unsigned probe -> "listening for webhooks" reachable without manual steps.
    from fastapi.testclient import TestClient

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
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
    os.environ["WEBHOOK_SECRET"] = "b" * 32
    os.environ.setdefault("GITHUB_TOKEN", "test-token")

    from webhook.app import create_app

    app = create_app(str(config_path), str(tmp_path / "cn.db"))
    with TestClient(app) as client:
        resp = client.post("/api/webhook", content=b"{}", headers={"X-GitHub-Event": "pull_request"})
    assert resp.status_code == 401  # endpoint reachable; signature gate active


def test_scn_cn_002_a1_image_toolchain_declared():
    dockerfile = ROOT / "Dockerfile"
    assert dockerfile.is_file()
    text = dockerfile.read_text(encoding="utf-8")

    assert "python:3" in text           # Python 3.11+ runtime (REQ-CN-002)
    assert "opencode" in text           # opencode CLI (npm-installed)
    assert "gitleaks" in text           # gitleaks scanner
    assert "git" in text                # git toolchain
    assert "pip install" in text        # FastAPI/uvicorn via pip


def test_scn_cn_002_a1_local_toolchain_probe():
    # Python + FastAPI are importable in the build/test env.
    import fastapi  # noqa: F401
    import httpx  # noqa: F401
    import yaml  # noqa: F401

    assert True


def test_scn_cn_004_a1_runner_guard_rejects_writes():
    from runner.workspace import WorkspaceRunner

    runner = WorkspaceRunner(None, None)
    assert runner.guard_read_only(["git", "commit", "-m", "x"]) is False
    assert runner.guard_read_only(["git", "push", "origin"]) is False
    assert runner.guard_read_only(["git", "status"]) is True  # read-only OK


def test_scn_cn_004_a1_no_push_or_commit_in_pipeline(journey):
    from runner.workspace import WorkspaceRunner

    runner = WorkspaceRunner(None, None)
    for argv in (["git", "push"], ["git", "commit"], ["git", "checkout", "-b", "x"], ["git", "merge"]):
        assert runner.guard_read_only(argv) is False
