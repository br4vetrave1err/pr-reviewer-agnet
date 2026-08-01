# Implements: ITP-006-A, ARCH-006, REQ-007, REQ-010, REQ-017, REQ-IF-003, REQ-CN-003
"""ITP-006-A: executor sandbox, CI-gate diagnosis, and skill-set injection."""

import subprocess

import pytest

from domain import Finding, ReviewResult, Severity
from executor.skills import SkillSetSelector
from queue.manager import QueueManager
from runner.workspace import WorkspaceRunner

from tests.integration.conftest import config, enqueue_decision, state


class _FakeProc:
    def __init__(self, rc=0, out=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = ""


@pytest.mark.asyncio
async def test_its_006_a1_workspace_run_parses_json_and_read_only(tmp_path, monkeypatch, config):
    from models.registry import ModelRegistry

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kw: _FakeProc(
            out='{"summary": "ok", "findings": [{"path": "a.py", "line": 1, '
            '"severity": "high", "title": "t", "detail": "d", "type": "bug"}]}'
        ),
    )
    runner = WorkspaceRunner(ModelRegistry(config), SkillSetSelector())
    assert runner.guard_read_only(["git", "push", "origin"]) is False  # writes blocked
    assert runner.guard_read_only(["git", "status"]) is True

    from runner.workspace import PromptContext

    result = await runner.run(
        str(tmp_path),
        PromptContext(
            head="abc", owner="acme", repo="app", pr=1, docs_text="", diff="",
            model_alias="free", auth_ref="X", skill_args=["/code-review"],
        ),
    )
    assert result.exit_code == 0
    assert len(result.findings) == 1  # output JSON parsed (REQ-IF-003)


@pytest.mark.asyncio
async def test_its_006_a2_failed_ci_queues_diagnosis_and_no_review(state, config, monkeypatch):
    diagnosis = []

    class FakeGithub:
        async def poll_check_runs(self, owner, repo, head):
            from github.client import CheckRun

            return [CheckRun(name="test", status="completed", conclusion="failure",
                             completed=True, failed=True)]

        async def fetch_failure_logs(self, owner, repo, pr, head):
            return "AssertionError: boom"

        async def post_comment(self, owner, repo, pr, body):
            diagnosis.append(body)

    from ci.gate import CiGateMonitor

    gate = CiGateMonitor(FakeGithub(), state, settle_seconds=0, poll_interval_seconds=0)
    manager = QueueManager(state, gate)

    run_id = manager.enqueue(enqueue_decision()).run_id
    job = state.get_run(run_id)
    gate.watch(job)

    await gate._watch(job)

    assert state.get_run(run_id).status == "ci-failed"  # REQ-010
    assert diagnosis  # diagnosis comment queued
    assert "AssertionError" in diagnosis[0]


def test_its_006_a3_skill_set_injected_per_findings(config):
    sel = SkillSetSelector(base_skill=config.agent_skill_set.base,
                           situational=config.agent_skill_set.situational)

    bug = Finding(path="x", severity=Severity.HIGH, title="b", type="bug")
    merge = Finding(path="x", severity=Severity.MEDIUM, title="m", type="merge_conflict")

    skills = sel.select([bug])
    assert "/code-review" in skills  # base always present (REQ-017)
    assert "/diagnosing-bugs" in skills  # bug finding -> situational skill

    skills2 = sel.select([merge], repo_skills=["/custom-repo-skill"])
    assert "/resolving-merge-conflicts" in skills2
    assert "/custom-repo-skill" in skills2  # repo skills unioned in

    assert sel.select([]) == ["/code-review"]  # bare review stays lean
