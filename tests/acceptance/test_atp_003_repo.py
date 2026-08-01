# Implements: ATP-003-A
"""ATP-003-A: managed-repo gating + denylist.

User journeys: a repo not in repo_config never triggers a review even on a
triggering event; a repo in both repo_config and the denylist is skipped even
though the trigger matched.
"""

import json

from config.load import validate as validate_config

from tests.acceptance.conftest import Journey, pull_request_payload


def _denylist_config():
    raw = {
        "providers": {
            "free": {"provider": "opencode", "model": "o3-mini", "enabled": True},
            "go": {"provider": "opencode-go", "model": "gpt-5", "enabled": True, "auth_env": "OPENCODE_GO_TOKEN"},
        },
        "default_model": "free",
        "repo_config": [{"owner": "acme", "repo": "app"}],
        "denylist": ["acme/app"],
        "agent_skill_set": {"base": "/code-review", "situational": ["/diagnosing-bugs", "/resolving-merge-conflicts"]},
    }
    return validate_config(json.loads(json.dumps(raw)))


def test_scn_003_a1_repo_not_managed_never_triggers(journey):
    payload = pull_request_payload(owner="not", repo="managed")
    status, _ = journey.deliver("pull_request", payload)

    assert status == 200  # acked but not enqueued
    assert journey.state.reconcile_open_jobs() == []
    assert journey.github.posted == 0


def test_scn_003_a2_denylisted_managed_repo_skipped(tmp_path):
    config = _denylist_config()
    journey = Journey(tmp_path, config)
    try:
        payload = pull_request_payload()  # managed (acme/app) but denylisted
        status, _ = journey.deliver("pull_request", payload)

        assert status == 200
        assert journey.state.reconcile_open_jobs() == []  # trigger matched, denied
        assert journey.github.posted == 0
    finally:
        journey.close()
