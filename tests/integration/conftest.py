# Implements: ITP-001-A, ITP-002-A, ITP-003-A, ITP-003-B, ITP-004-A, ITP-005-A, ITP-006-A, ITP-007-A, ITP-008-A, ITP-009-A, ITP-010-A, ITP-011-A, ITP-012-A, ITP-013-A
"""Shared integration-test fixtures (architecture-level wiring)."""

import os

import pytest

from config.load import validate as validate_config
from domain import Decision, NormalizedEvent
from filter.trigger import TriggerDecisionEngine
from queue.manager import QueueManager
from state.db import StateRepository

VALID_CONFIG_RAW = {
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
    return validate_config(dict(VALID_CONFIG_RAW))


@pytest.fixture()
def state(tmp_path):
    s = StateRepository(str(tmp_path / "it.db"))
    yield s
    s.close()


class FakeCiGate:
    def __init__(self):
        self.watched = []

    def watch(self, job):
        self.watched.append(job.run_id)


@pytest.fixture()
def manager(state):
    return QueueManager(state, FakeCiGate(), max_attempts=3)


@pytest.fixture()
def trigger(config):
    return TriggerDecisionEngine(config, self_account="reviewer-bot")


@pytest.fixture()
def author_event():
    return NormalizedEvent(
        event="pull_request", action="opened", owner="acme", repo="app",
        pr_number=1, head_sha="abc123", author="reviewer-bot",
        requested_reviewers=[], pr_state="open", sender="reviewer-bot",
    )


def enqueue_decision(pr=1, head="abc123"):
    return Decision(action="enqueue", owner="acme", repo="app", pr=pr, head=head)


def sign_payload(secret, payload):
    import hashlib
    import hmac

    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def pull_request_payload(owner="acme", repo="app", pr=1, head="abc123", author="reviewer-bot", state="open", action="opened"):
    return {
        "action": action,
        "repository": {"owner": {"login": owner}, "name": repo},
        "pull_request": {
            "number": pr,
            "head": {"sha": head},
            "user": {"login": author},
            "state": state,
            "requested_reviewers": [],
        },
        "sender": {"login": author},
    }


@pytest.fixture(autouse=True)
def _env():
    os.environ.setdefault("GITHUB_TOKEN", "test-token")
    yield
