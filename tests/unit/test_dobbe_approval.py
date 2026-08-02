"""Unit test — Dobbe-AI approval requirements and automatic PR reviews."""

import pytest
from config.load import load_config, validate
from queue.manager import ReviewJob
from executor.pipeline import ReviewPipeline


def test_dobbe_ai_config_requires_approval():
    config = load_config("config.yaml")
    assert config.requires_approval("Dobbe-AI", "Dobbe-AI") is True
    assert config.can_auto_merge("Dobbe-AI", "Dobbe-AI") is False


def test_regular_repo_approval_defaults():
    raw = {
        "providers": {"free": {"provider": "opencode", "model": "o3-mini", "enabled": True}},
        "default_model": "free",
        "repo_config": [
            {"owner": "acme", "repo": "app"},
            {"owner": "Dobbe-AI", "repo": "Dobbe-AI", "require_approval": True, "auto_merge": False},
        ],
    }
    cfg = validate(raw)
    assert cfg.requires_approval("acme", "app") is False
    assert cfg.can_auto_merge("acme", "app") is True
    assert cfg.requires_approval("Dobbe-AI", "Dobbe-AI") is True
    assert cfg.can_auto_merge("Dobbe-AI", "Dobbe-AI") is False


@pytest.mark.asyncio
async def test_publish_approved_review_blocks_unapproved_dobbe_ai_action():
    raw = {
        "providers": {"free": {"provider": "opencode", "model": "o3-mini", "enabled": True}},
        "default_model": "free",
        "repo_config": [
            {"owner": "Dobbe-AI", "repo": "Dobbe-AI", "require_approval": True, "auto_merge": False},
        ],
    }
    cfg = validate(raw)

    actions_taken = []

    class FakeGithub:
        async def submit_review(self, *args, **kwargs):
            actions_taken.append(("submit_review", kwargs))

        async def mark_pr_ready_for_review(self, owner, repo, pr):
            actions_taken.append(("mark_pr_ready", owner, repo, pr))

        async def merge_pr(self, owner, repo, pr):
            actions_taken.append(("merge_pr", owner, repo, pr))

    pipeline = ReviewPipeline(
        clone_cache=None, docs_loader=None, workspace_runner=None,
        compliance_validator=None, security_scanner=None, llm_reviewer=None,
        github_client=FakeGithub(), skills_selector=None, config=cfg
    )

    job = ReviewJob(run_id="run-1", owner="Dobbe-AI", repo="Dobbe-AI", pr=42, head="sha123")

    # Without user_approved=True, actions on Dobbe-AI are blocked
    await pipeline.publish_approved_review(job, summary="test", findings=[], is_draft=True, auto_merge=True, user_approved=False)
    assert actions_taken == []

    # With user_approved=True, actions execute
    await pipeline.publish_approved_review(job, summary="test", findings=[], is_draft=True, auto_merge=False, user_approved=True)
    assert len(actions_taken) >= 1
    assert actions_taken[0][0] == "submit_review"
