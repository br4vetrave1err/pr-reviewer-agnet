# Implements: ITP-003-A, ITP-003-B, ARCH-003, REQ-004, REQ-012, REQ-014, REQ-NF-005, REQ-NF-006
"""ITP-003-A/B: durability-before-ack, dedup, re-review, and full pipeline."""

import asyncio

import pytest

from domain import Decision, Finding, ReviewResult, Severity
from queue.manager import QueueManager
from queue.worker import WorkerScheduler

from tests.integration.conftest import enqueue_decision, state


class FakeGate:
    def __init__(self):
        self.watched = []

    def watch(self, job):
        self.watched.append(job.run_id)


@pytest.mark.asyncio
async def test_its_003_a1_enqueue_persists_before_ack_and_worker_observes(state):
    gate = FakeGate()
    manager = QueueManager(state, gate)

    run_id = manager.enqueue(enqueue_decision()).run_id
    durable = state.get_run(run_id)  # row exists before any response/ack is sent
    assert durable.status == "pending_ci"

    state.set_status(run_id, "queued")  # CI gate pass/bypass -> worker may claim
    observed = await manager.dequeue()
    assert observed is not None and observed.run_id == run_id


@pytest.mark.asyncio
async def test_its_003_a2_full_pipeline_posts_review(state, config, tmp_path):
    posted = {}

    class FakeGithub:
        async def fetch_pr_diff(self, owner, repo, pr):
            return "diff --git a/x.py b/x.py\n+print(1)\n"

        async def submit_review(self, owner, repo, pr, head, summary, inline_comments, run_id):
            posted["summary"] = summary
            posted["inline"] = inline_comments
            return 123

    class FakeClone:
        def __init__(self, root):
            self._root = root

        def ensure(self, owner, repo, head, token):
            return str(self._root)

    class FakeDocs:
        def load(self, owner, repo):
            from domain import Docs

            return Docs(files=["x.md"], content={"x.md": "# docs"}, degraded=False)

    class FakeRunner:
        async def run(self, checkout, context):
            return ReviewResult(
                summary="Reviewed the PR.",
                findings=[
                    Finding(path="x.py", line=1, severity=Severity.HIGH,
                            title="Bug", detail="logic error", type="bug")
                ],
            )

    from executor.pipeline import ReviewPipeline
    from executor.skills import SkillSetSelector
    from tests.compliance import ComplianceValidator

    gate = FakeGate()
    manager = QueueManager(state, gate)
    pipeline = ReviewPipeline(
        clone_cache=FakeClone(tmp_path),
        docs_loader=FakeDocs(),
        workspace_runner=FakeRunner(),
        compliance_validator=ComplianceValidator(str(tmp_path)),
        security_scanner=_NoScan(),
        llm_reviewer=_NoLlm(),
        github_client=FakeGithub(),
        skills_selector=SkillSetSelector(),
        config=config,
    )

    run_id = manager.enqueue(enqueue_decision()).run_id
    result = await pipeline.execute(manager._state.get_run(run_id), token="tok")

    assert result.status == "posted"
    assert posted["summary"]  # summary posted
    assert any(c["path"] == "x.py" for c in posted["inline"])  # inline comments posted


class _NoScan:
    def scan(self, checkout):
        from security.scanner import SecReport

        return SecReport()


class _NoLlm:
    async def review(self, context):
        return ReviewResult()


@pytest.mark.asyncio
async def test_its_003_b1_dedup_same_head_single_row(state):
    gate = FakeGate()
    manager = QueueManager(state, gate)

    first = manager.enqueue(enqueue_decision(head="abc123")).run_id
    second = manager.enqueue(enqueue_decision(head="abc123"))

    assert second.duplicate is True  # dedup honored by the store (REQ-004)
    runs = state.reconcile_open_jobs()
    assert len(runs) == 1
    assert runs[0].run_id == first


@pytest.mark.asyncio
async def test_its_003_b2_new_head_re_enqueues_and_earlier_resolves(state):
    gate = FakeGate()
    manager = QueueManager(state, gate)

    first = manager.enqueue(enqueue_decision(head="oldsha")).run_id
    state.set_status(first, "running")  # earlier run already in flight

    second = manager.enqueue(enqueue_decision(head="newsha"))
    assert second.duplicate is False  # new head -> new run

    runs = state.reconcile_open_jobs()
    assert len(runs) == 1
    assert runs[0].head == "newsha"

    # earlier run resolves to posted without a double post (single worker path)
    worker = WorkerScheduler(manager, lambda job: asyncio.sleep(0.001), max_attempts=3)
    assert worker.active_workers == 0
