# Implements: STP-001-A, STP-001-B, STP-002-A, STP-003-A, STP-003-B, STP-004-A, STP-005-A, STP-005-B, STP-006-A, STP-006-B, STP-007-A, STP-008-A, STP-009-A, STP-010-A, STP-011-A, STP-012-A, STP-013-A, STP-014-A, STP-014-B
"""Shared system-test fixtures (architectural behavior at component level)."""

import os

import pytest

from config.load import validate as validate_config
from state.db import StateRepository

SYSTEM_CONFIG_RAW = {
    "providers": {
        "free": {"provider": "opencode", "model": "o3-mini", "enabled": True},
        "go": {"provider": "opencode-go", "model": "gpt-5", "enabled": True, "auth_env": "OPENCODE_GO_TOKEN"},
    },
    "default_model": "free",
    "repo_config": [{"owner": "acme", "repo": "app"}],
    "agent_skill_set": {"base": "/code-review", "situational": ["/diagnosing-bugs", "/resolving-merge-conflicts"]},
}


@pytest.fixture()
def config():
    return validate_config(dict(SYSTEM_CONFIG_RAW))


@pytest.fixture()
def state(tmp_path):
    s = StateRepository(str(tmp_path / "sys.db"))
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _env():
    os.environ.setdefault("GITHUB_TOKEN", "test-token")
    yield


def review_job(owner="acme", repo="app", pr=1, head="abc123", model=None, status="pending_ci", attempts=0):
    from queue.manager import ReviewJob

    return ReviewJob(owner=owner, repo=repo, pr=pr, head=head, model=model, status=status, attempts=attempts)
