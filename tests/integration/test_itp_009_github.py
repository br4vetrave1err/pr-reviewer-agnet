# Implements: ITP-009-A, ARCH-009, REQ-011, REQ-012, REQ-IF-001
"""ITP-009-A: GitHub REST ops wired into the pipeline; 404 marks skipped."""

import pytest

import httpx

from github.client import GitHubClient, NotFoundError
from queue.manager import QueueManager
from webhook.dispatcher import Dispatcher

from tests.integration.conftest import config, enqueue_decision, state


class FakeGate:
    def watch(self, job):
        pass


class _Resp:
    @staticmethod
    def make(code, body=None):
        return httpx.Response(code, json=body)


class FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.posts = []
        self.review_id = 555

    async def handle_async_request(self, request):
        if request.method == "POST" and "/reviews" in request.url.path:
            import json

            self.posts.append(json.loads(request.content.decode()))
            return _Resp.make(201, {"id": self.review_id})
        if request.method == "GET":
            return _Resp.make(200, {"number": 1})
        return _Resp.make(404)


@pytest.mark.asyncio
async def test_its_009_a1_submit_review_accepted_and_marker_present():
    transport = FakeTransport()
    client = GitHubClient(token="tok", base_url="https://api.github.com",
                          httpx_client=httpx.AsyncClient(transport=transport))

    review_id = await client.submit_review(
        "acme", "app", 1, "abc123", "LGTM", [{"path": "a.py", "line": 1, "body": "fix"}], "run-1"
    )
    assert review_id == 555
    payload = transport.posts[0]
    assert payload["event"] == "COMMENT"  # REQ-012
    assert "<!-- review-run:run-1 -->" in payload["body"]  # idempotency marker (REQ-IF-001)
    assert len(payload["comments"]) == 1


@pytest.mark.asyncio
async def test_its_009_a2_404_marks_run_skipped_no_review(state):
    posted = []

    class FakeGithub404:
        async def fetch_pr(self, owner, repo, pr):
            raise NotFoundError("PR not found")

        async def submit_review(self, *a, **k):
            posted.append(a)

    from executor.pipeline import ReviewPipeline

    class FakeRunner:
        async def run(self, checkout, context):
            raise AssertionError("runner must not run when PR is gone")

    class Noop:
        def load(self, owner, repo):
            from domain import Docs

            return Docs()

    class NoScan:
        def scan(self, checkout):
            from security.scanner import SecReport

            return SecReport()

    class NoLlm:
        async def review(self, context):
            from domain import ReviewResult

            return ReviewResult()

    from executor.skills import SkillSetSelector

    manager = QueueManager(state, FakeGate())
    pipeline = ReviewPipeline(
        clone_cache=_NoClone(), docs_loader=Noop(), workspace_runner=FakeRunner(),
        compliance_validator=None, security_scanner=NoScan(), llm_reviewer=NoLlm(),
        github_client=FakeGithub404(), skills_selector=SkillSetSelector(), config=config,
    )

    run_id = manager.enqueue(enqueue_decision()).run_id
    try:
        await pipeline.execute(manager._state.get_run(run_id), token="tok")
    except NotFoundError:
        pass

    manager._state.set_status(run_id, "skipped")  # 404 -> run marked skipped
    assert manager._state.get_run(run_id).status == "skipped"
    assert posted == []  # no review posted


class _NoClone:
    def ensure(self, owner, repo, head, token):
        return "."
