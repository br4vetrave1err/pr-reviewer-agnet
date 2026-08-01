# Implements: MOD-001, MOD-002, MOD-004, MOD-005, ARCH-001, ARCH-003, SYS-001, SYS-003, SYS-014, REQ-CN-002, REQ-NF-001, REQ-NF-007
"""FastAPI application assembly (boot wiring).

Wires the webhook handler, dispatcher, queue manager, worker, pipeline, and
state into a single FastAPI app. Boot is fail-closed: an invalid config
refuses to start (REQ-IF-004). Graceful shutdown stops the worker loop
(REQ-CN-002).
"""

from __future__ import annotations

import asyncio
import logging
import os

from queue.manager import QueueManager
from queue.worker import WorkerScheduler

from fastapi import FastAPI, Header, Request

from cache.clone import CloneCacheManager
from ci.gate import CiGateMonitor
from config.load import load_config
from docs.loader import DocsLoader
from executor.pipeline import ReviewPipeline
from executor.skills import SkillSetSelector
from filter.trigger import TriggerDecisionEngine
from github.client import GitHubClient
from models.registry import ModelRegistry
from runner.workspace import WorkspaceRunner
from security.llm import LlmSecurityReviewer
from security.scanner import SecurityScanRunner
from state.db import StateRepository
from tests.compliance import ComplianceValidator
from webhook.dispatcher import Dispatcher
from webhook.handler import WebhookHandler, router

log = logging.getLogger("pr_reviewer.app")


def create_app(config_path: str = "config.yaml", db_path: str = ".state/pr_reviewer.db") -> FastAPI:
    config = load_config(config_path)  # fail-closed at boot (REQ-IF-004)
    state = StateRepository(db_path)

    github = GitHubClient()
    registry = ModelRegistry(config)
    skills = SkillSetSelector(
        base_skill=config.agent_skill_set.base,
        situational=config.agent_skill_set.situational,
    )
    clone_cache = CloneCacheManager(config.workspace_cache_dir, state, config.disk_cap_bytes)
    docs = DocsLoader(config.specs_docs_dir)
    runner = WorkspaceRunner(registry, skills)
    compliance = ComplianceValidator(".")
    scanner = SecurityScanRunner()
    llm = LlmSecurityReviewer(runner)
    ci_gate = CiGateMonitor(github, state, config.ci_gate.settle_seconds, config.ci_gate.wait_cap_minutes)
    queue = QueueManager(state, ci_gate, config.retry.max_attempts)
    ci_gate.attach(queue)
    pipeline = ReviewPipeline(
        clone_cache, docs, runner, compliance, scanner, llm, github, skills, config
    )

    def _execute(job):
        """Worker calls pipeline(job); token comes from the runtime env (ARCH-003)."""
        return pipeline.execute(job, token=os.environ.get("GITHUB_TOKEN", ""))

    worker = WorkerScheduler(queue, _execute, config.retry.max_attempts)

    self_account = os.environ.get("PR_REVIEWER_ACCOUNT", "")
    trigger = TriggerDecisionEngine(config, self_account)
    dispatcher = Dispatcher(trigger, queue)
    handler = WebhookHandler(_secret_provider(config), dispatcher, self_account)

    app = FastAPI(title="PR Review Agent")
    app.include_router(router)

    @app.post("/api/webhook")
    async def webhook(request: Request, x_hub_signature_256: str | None = Header(default=None)):
        return await handler.handle(request, x_hub_signature_256)

    @app.on_event("startup")
    async def startup() -> None:
        queue.reconcile()  # ARCH-011 boot sweep
        app.state.worker_task = asyncio.create_task(worker.run())

    @app.on_event("shutdown")
    async def shutdown() -> None:
        task = getattr(app.state, "worker_task", None)
        if task is not None:
            task.cancel()
        state.close()

    return app


def _secret_provider(config):
    async def secret() -> str:
        return os.environ.get(config.webhook_secret_env, "")

    return secret
