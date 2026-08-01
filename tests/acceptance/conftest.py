# Implements: ATP-001-A, ATP-001-B, ATP-002-A, ATP-003-A, ATP-004-A, ATP-005-A, ATP-006-A, ATP-007-A, ATP-008-A, ATP-009-A, ATP-010-A, ATP-011-A, ATP-012-A, ATP-013-A, ATP-014-A, ATP-015-A, ATP-016-A, ATP-017-A, ATP-NF-001-A, ATP-NF-002-A, ATP-NF-003-A, ATP-NF-004-A, ATP-NF-005-A, ATP-NF-006-A, ATP-NF-007-A, ATP-IF-001-A, ATP-IF-002-A, ATP-IF-003-A, ATP-IF-004-A, ATP-IF-005-A, ATP-IF-006-A, ATP-CN-001-A, ATP-CN-002-A, ATP-CN-003-A, ATP-CN-004-A
"""Shared acceptance-test fixtures: a full user-journey harness.

Wires the real webhook handler, dispatcher, queue manager, worker scheduler,
and the real ReviewPipeline — with fake GitHub client, fake clone cache, and
fake opencode runner — so a signed webhook delivery flows end-to-end to a
posted review. Acceptance tests exercise whole journeys, not components.
"""

import asyncio
import hashlib
import hmac
import json
import os
import time

import pytest

from cache.clone import CloneCacheManager
from ci.gate import CiGateMonitor
from config.load import validate as validate_config
from domain import Finding, ReviewResult, Severity
from docs.loader import DocsLoader
from executor.pipeline import ReviewPipeline
from executor.skills import SkillSetSelector
from filter.command import usage
from filter.trigger import TriggerDecisionEngine
from models.registry import ModelRegistry
from queue.manager import QueueManager
from queue.worker import WorkerScheduler
from runner.workspace import PromptContext, WorkspaceRunner
from security.llm import LlmSecurityReviewer
from security.scanner import SecurityScanRunner
from state.db import StateRepository
from tests.compliance import ComplianceValidator
from webhook.dispatcher import Dispatcher
from webhook.handler import WebhookHandler

ACCEPTANCE_CONFIG_RAW = {
    "providers": {
        "free": {"provider": "opencode", "model": "o3-mini", "enabled": True},
        "go": {"provider": "opencode-go", "model": "gpt-5", "enabled": True, "auth_env": "OPENCODE_GO_TOKEN"},
        "gemini": {"provider": "google-one", "model": "gemini-2.5-pro", "enabled": False, "auth_env": "OPENCODE_GO_TOKEN"},
    },
    "default_model": "free",
    "switch_default": "go",
    "repo_config": [{"owner": "acme", "repo": "app"}],
    "denylist": [],
    "defaults": {"concurrency": 1},
    "agent_skill_set": {"base": "/code-review", "situational": ["/diagnosing-bugs", "/resolving-merge-conflicts"]},
}

SECRET = "b" * 32
SELF_ACCOUNT = "reviewer-bot"


@pytest.fixture()
def config():
    return validate_config(json.loads(json.dumps(ACCEPTANCE_CONFIG_RAW)))


@pytest.fixture()
def state(tmp_path):
    s = StateRepository(str(tmp_path / "acc.db"))
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _env():
    os.environ.setdefault("GITHUB_TOKEN", "test-token")
    yield


def sign_payload(secret, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


class _Missing:
    """Sentinel: deliver a webhook with no X-Hub-Signature-256 header."""


MISSING_SIGNATURE = _Missing()


def pull_request_payload(owner="acme", repo="app", pr=1, head="abc123", author="reviewer-bot", action="opened", state="open"):
    return json.dumps({
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
    }).encode()


def comment_payload(body, owner="acme", repo="app", pr=1, head="abc123", author="reviewer-bot"):
    return json.dumps({
        "action": "created",
        "repository": {"owner": {"login": owner}, "name": repo},
        "pull_request": {"number": pr, "head": {"sha": head}},
        "comment": {"user": {"login": author}, "body": body},
        "sender": {"login": author},
    }).encode()


def check_run_payload(owner="acme", repo="app", pr=1, head="abc123", conclusion="success"):
    return json.dumps({
        "action": "completed",
        "repository": {"owner": {"login": owner}, "name": repo},
        "pull_request": {"number": pr, "head": {"sha": head}},
        "check_run": {"status": "completed", "conclusion": conclusion},
        "sender": {"login": "ci"},
    }).encode()


def wait_for(predicate, deadline=3.0):
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not met within %.1fs" % deadline)


class FakeGithub:
    """In-memory GitHub stand-in recording every outbound call (ATP-IF-001-A)."""

    def __init__(self, check_runs=None, diff="--- a/src/foo.py\n+++ b/src/foo.py\n@@ -1 +1 @@\n-x\n+y\n"):
        self.check_runs = check_runs or []
        self.diff = diff
        self.reviews = []
        self.comments = []
        self.posted = 0

    async def fetch_pr_diff(self, owner, repo, pr):
        return self.diff

    async def submit_review(self, owner, repo, pr, head, summary, inline, run_id):
        self.reviews.append({"summary": summary, "inline": inline, "run_id": run_id})
        self.posted += 1
        return self.posted

    async def post_comment(self, owner, repo, pr, body):
        self.comments.append(body)

    async def poll_check_runs(self, owner, repo, head):
        return self.check_runs

    async def fetch_failure_logs(self, owner, repo, pr, head):
        return "Traceback: division by zero"


class FakeCloneCache:
    """Fake clone cache returning a scratch checkout dir (REQ-CN-004)."""

    def __init__(self, root):
        self.root = root
        self.ensured = []

    def ensure(self, owner, repo, head, token):
        self.ensured.append((owner, repo, head))
        d = os.path.join(self.root, owner, repo)
        os.makedirs(d, exist_ok=True)
        return d


class FakeRunner(WorkspaceRunner):
    """Fake opencode runner; records the model/skills it was given."""

    def __init__(self, result=None):
        super().__init__(None, None)
        self.result = result or ReviewResult(summary="Review complete.", findings=[])
        self.calls = []

    async def run(self, checkout, context: PromptContext):
        self.calls.append(context)
        return self.result

    async def security_step(self, prompt):
        return ReviewResult(summary="", findings=[])


class FakeScanner:
    def should_scan(self, ci_status):
        return ci_status in (None, "success", "green")

    def scan(self, checkout):
        from security.scanner import SecReport

        return SecReport()


class Journey:
    """Full-stack harness: deliver signed webhooks, inspect the outcome.

    Mirrors ``webhook.app.create_app`` wiring but with fakes injected for the
    external boundaries (GitHub, opencode, gitleaks, clone cache).
    """

    def __init__(self, tmp_path, config, github=None, runner=None, scanner=None, secret=SECRET):
        self._tmp = tmp_path
        self._config = config
        self._secret = secret
        self.github = github or FakeGithub()
        self.runner = runner or FakeRunner()
        self.scanner = scanner or FakeScanner()

        self.state = StateRepository(str(tmp_path / "journey.db"))
        self.registry = ModelRegistry(config)
        self.skills = SkillSetSelector(config.agent_skill_set.base, config.agent_skill_set.situational)
        self.clone_cache = FakeCloneCache(str(tmp_path / "checkouts"))
        self.docs = DocsLoader(str(tmp_path / "specs"))
        self.compliance = ComplianceValidator(str(tmp_path))
        self.ci_gate = CiGateMonitor(self.github, self.state, settle_seconds=0, poll_interval_seconds=0)
        self.queue = QueueManager(self.state, self.ci_gate, max_attempts=3)
        self.ci_gate.attach(self.queue)
        self.pipeline = ReviewPipeline(
            self.clone_cache, self.docs, self.runner, self.compliance,
            self.scanner, LlmSecurityReviewer(self.runner),
            self.github, self.skills, config,
        )
        self.worker = WorkerScheduler(self.queue, self._execute, max_attempts=3)
        self.trigger = TriggerDecisionEngine(config, SELF_ACCOUNT)
        self.reply_comments = []

        from domain import Decision
        from filter.command import usage
        from models.registry import UnknownAliasError

        async def reply_post(decision):
            valid = self.registry.valid_aliases()
            if decision.model is not None:
                try:
                    self.registry.resolve(decision.model)
                except UnknownAliasError:
                    self.reply_comments.append(usage(valid))
                    return
            if not (decision.owner and decision.repo and decision.pr is not None):
                self.reply_comments.append(usage(valid))
                return
            self.queue.enqueue(
                Decision(
                    action="enqueue",
                    owner=decision.owner,
                    repo=decision.repo,
                    pr=decision.pr,
                    head=decision.head,
                    model=decision.model,
                ),
                cause="comment",
            )

        self.dispatcher = Dispatcher(self.trigger, self.queue, reply_post=reply_post)
        self.handler = WebhookHandler(_secret_provider(self), self.dispatcher, SELF_ACCOUNT)

    def close(self):
        self.state.close()

    def deliver(self, event, payload, sig_override=None):
        """Synchronously deliver a webhook; return (status_code, elapsed_s)."""
        from fastapi import FastAPI, Header, Request
        from fastapi.testclient import TestClient

        app = FastAPI()

        @app.post("/api/webhook")
        async def webhook(request: Request, x_hub_signature_256: str | None = Header(default=None)):
            return await self.handler.handle(request, x_hub_signature_256)

        headers = {"X-GitHub-Event": event}
        if isinstance(sig_override, str) and sig_override:
            headers["X-Hub-Signature-256"] = sig_override
        elif sig_override is None:
            headers["X-Hub-Signature-256"] = sign_payload(self._secret, payload)

        with TestClient(app) as client:
            start = time.monotonic()
            resp = client.post("/api/webhook", content=payload, headers=headers)
            elapsed = time.monotonic() - start
        return resp.status_code, elapsed

    def _execute(self, job):
        """Bind the worker to the pipeline with a synthetic token (REQ-014)."""
        return self.pipeline.execute(job, token=os.environ.get("GITHUB_TOKEN", "test-token"))

    async def deliver_async(self, payload, event="pull_request", sig_override=None):
        """Deliver a webhook inside the current event loop (same-loop dispatch).

        Runs the app over an in-process ASGI transport so the enqueue, CI-gate
        watch, and reply tasks share the test loop — required by the pipeline
        journeys that drive the worker afterwards.
        """
        import httpx
        from fastapi import FastAPI, Header, Request

        app = FastAPI()

        @app.post("/api/webhook")
        async def webhook(request: Request, x_hub_signature_256: str | None = Header(default=None)):
            return await self.handler.handle(request, x_hub_signature_256)

        headers = {"X-GitHub-Event": event}
        if isinstance(sig_override, str) and sig_override:
            headers["X-Hub-Signature-256"] = sig_override
        elif sig_override is None:
            headers["X-Hub-Signature-256"] = sign_payload(self._secret, payload)

        transport = httpx.ASGITransport(app=app)
        start = time.monotonic()
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/webhook", content=payload, headers=headers)
            elapsed = time.monotonic() - start
        return resp.status_code, elapsed

    async def wait_until(self, predicate, timeout=3.0):
        """Async poll for a condition (the event loop keeps running)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if predicate():
                return
            await asyncio.sleep(0.02)
        raise AssertionError("condition not met within %.1fs" % timeout)

    async def run_until(self, predicate, timeout=3.0):
        """Run the worker in the current loop until a condition holds, then stop."""
        task = asyncio.create_task(self.worker.run())
        try:
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                if predicate():
                    return
                await asyncio.sleep(0.02)
            raise AssertionError("condition not met within %.1fs" % timeout)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def drain_worker(self, seconds=0.3):
        task = asyncio.create_task(self.worker.run())
        await asyncio.sleep(seconds)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def _secret_provider(journey):
    async def secret():
        return journey._secret

    return secret


@pytest.fixture()
def journey(tmp_path, config):
    j = Journey(tmp_path, config)
    yield j
    j.close()


def high_finding(path="src/foo.py", line=3):
    return Finding(path=path, line=line, severity=Severity.HIGH, title="auth bypass", type="bug")
