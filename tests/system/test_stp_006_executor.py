# Implements: STP-006-A, STP-006-B, SYS-006, REQ-007, REQ-010, REQ-017, REQ-IF-003, REQ-CN-003
"""STP-006-A/B: headless opencode contract, read-only, skills, and CI gate."""

import subprocess

import pytest
from domain import Decision, Finding, Severity
from executor.skills import SkillSetSelector
from models.registry import ModelRegistry
from runner.workspace import PromptContext, WorkspaceRunner

from tests.system.conftest import config, state, review_job


class _FakeProc:
    def __init__(self, rc=0, out=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = ""


@pytest.mark.asyncio
async def test_sts_006_a1_headless_opencode_contract(tmp_path, monkeypatch, config):
    argv = []

    def fake_run(cmd, **kw):
        argv.append(cmd)
        return _FakeProc(out='{"summary": "ok", "findings": []}')

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = WorkspaceRunner(ModelRegistry(config), SkillSetSelector())
    result = await runner.run(
        str(tmp_path),
        PromptContext(
            head="h", owner="acme", repo="app", pr=1, docs_text="",
            diff="", model_alias="free", auth_ref="X", skill_args=["/code-review"],
        ),
    )
    assert result.exit_code == 0
    assert argv[0][0] in {"opencode", "agy"} and argv[0][1] == "run"  # one-off CLI subprocess


def test_sts_006_a2_read_only_enforced(config):
    runner = WorkspaceRunner(None, None)
    assert runner.guard_read_only(["git", "commit", "-m", "x"]) is False
    assert runner.guard_read_only(["git", "push", "origin"]) is False
    assert runner.guard_read_only(["git", "checkout", "-b", "feature"]) is False
    assert runner.guard_read_only(["git", "status"]) is True  # read-only OK


def test_sts_006_a3_skill_set_assembled(config):
    sel = SkillSetSelector(
        base_skill=config.agent_skill_set.base,
        situational=config.agent_skill_set.situational,
    )
    findings = [
        Finding(path="a", severity=Severity.HIGH, type="bug"),
        Finding(path="b", severity=Severity.MEDIUM, type="merge_conflict"),
    ]
    skills = sel.select(findings, repo_skills=["/repo-skill"])
    assert "/code-review" in skills
    assert "/diagnosing-bugs" in skills
    assert "/resolving-merge-conflicts" in skills
    assert "/repo-skill" in skills


class _FakeGithub:
    def __init__(self, runs):
        self._runs = runs
        self.comments = []
        self.reviews = []

    async def poll_check_runs(self, owner, repo, head):
        return self._runs

    async def fetch_failure_logs(self, owner, repo, pr, head):
        return "Traceback: division by zero"

    async def post_comment(self, owner, repo, pr, body):
        self.comments.append(body)

    async def submit_review(self, *a, **k):
        self.reviews.append(a)


def _gate_failure_check():
    from github.client import CheckRun

    return [CheckRun(name="t", status="completed", conclusion="failure", completed=True, failed=True)]


class _FakeGate:
    def watch(self, job):
        pass


@pytest.mark.asyncio
async def test_sts_006_b1_failed_ci_diagnosis_not_review(state):
    from ci.gate import CiGateMonitor
    from queue.manager import QueueManager

    fake = _FakeGithub(_gate_failure_check())
    gate = CiGateMonitor(fake, state, settle_seconds=0, poll_interval_seconds=0)
    manager = QueueManager(state, _FakeGate())
    job = review_job(status="pending_ci")
    run_id = manager.enqueue(_decision(job)).run_id
    await gate._watch(state.get_run(run_id))

    assert state.get_run(run_id).status == "ci-failed"  # REQ-010
    assert fake.comments  # diagnosis comment queued
    assert fake.reviews == []  # no review produced


@pytest.mark.asyncio
async def test_sts_006_b2_no_ci_bypass_after_settle(state):
    from ci.gate import CiGateMonitor
    from queue.manager import QueueManager

    fake = _FakeGithub([])
    gate = CiGateMonitor(fake, state, settle_seconds=0, poll_interval_seconds=0)
    manager = QueueManager(state, _FakeGate())
    job = review_job(status="pending_ci")
    run_id = manager.enqueue(_decision(job)).run_id
    await gate._watch(state.get_run(run_id))

    assert state.get_run(run_id).status == "queued"  # no-CI bypass -> review proceeds


def _decision(job):
    return Decision(action="enqueue", owner=job.owner, repo=job.repo, pr=job.pr, head=job.head)
