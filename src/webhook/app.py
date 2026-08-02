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
from webhook.registrar import WebhookRegistrar
from queue.backfill import BootBackfill
from observability.configurator import LoggingConfigurator

log = logging.getLogger("pr_reviewer.app")


def create_app(config_path: str = "config.yaml", db_path: str = ".runs/pr_reviewer.db") -> FastAPI:
    LoggingConfigurator.configure()
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
    from observability.slack_notifier import SlackNotifier
    slack = SlackNotifier()

    pipeline = ReviewPipeline(
        clone_cache, docs, runner, compliance, scanner, llm, github, skills, config, slack_notifier=slack
    )

    def _execute(job):
        """Worker calls pipeline(job); token comes from the runtime env (ARCH-003)."""
        return pipeline.execute(job, token=os.environ.get("GITHUB_TOKEN", ""))

    worker = WorkerScheduler(queue, _execute, config.retry.max_attempts)

    async def _reply_post(decision):
        if decision.action == "notify-merged":
            await slack.notify_review_approved_and_promoted(
                run_id=decision.head or "merged",
                owner=decision.owner or "",
                repo=decision.repo or "",
                pr=decision.pr or 0,
                is_draft=False,
                merged=True,
            )
        elif decision.reason == "malformed-command":
            from filter.command import usage
            await github.post_comment(
                decision.owner, decision.repo, decision.pr, usage(registry.valid_aliases())
            )
        else:
            queue.enqueue(decision, cause="comment")

    self_account = os.environ.get("PR_REVIEWER_ACCOUNT", "")
    trigger = TriggerDecisionEngine(config, self_account)
    dispatcher = Dispatcher(trigger, queue, _reply_post)
    handler = WebhookHandler(_secret_provider(config), dispatcher, self_account)
    registrar = WebhookRegistrar(
        config,
        github,
        secret=os.environ.get(config.webhook_secret_env, ""),
        ngrok_agent_url=config.ngrok_agent_url,
    )
    backfill = BootBackfill(config, github, trigger, dispatcher, state)

    app = FastAPI(title="PR Review Agent")
    app.include_router(router)

    @app.post("/api/webhook")
    async def webhook(request: Request, x_hub_signature_256: str | None = Header(default=None)):
        return await handler.handle(request, x_hub_signature_256)

    @app.post("/api/reviews/{run_id}/approve")
    async def approve_staged_review(run_id: str, owner: str | None = None, repo: str | None = None, pr: int | None = None):
        """REQ-021, REQ-022: Approve a staged pending_approval review, release to GitHub, and auto-merge."""
        log.info("approve_staged_review", extra={"event": "approve_staged_review", "run_id": run_id, "owner": owner, "repo": repo, "pr": pr})
        job = state.get_job(run_id)
        if not job and owner and repo and pr:
            from queue.manager import ReviewJob
            job = ReviewJob(run_id=run_id, owner=owner, repo=repo, pr=pr, head="")
        if job:
            asyncio.create_task(pipeline.publish_approved_review(job, summary="Review Approved via Agent", findings=[], is_draft=True, auto_merge=True))
            return {"status": "approved", "run_id": run_id, "message": f"Review {run_id} approved! Auto-merging PR #{job.pr} on GitHub."}
        return {"status": "approved", "run_id": run_id, "message": "Review approval acknowledged."}

    @app.post("/api/slack/events")
    async def slack_events(request: Request):
        """REQ-025: 2-Way Slack Events API endpoint (url_verification & app_mention commands)."""
        try:
            body = await request.json()
        except Exception:
            return {"status": "bad_request"}
        if body.get("type") == "url_verification":
            return {"challenge": body.get("challenge", "")}
        if body.get("type") == "event_callback":
            event = body.get("event", {})
            if event.get("type") in {"app_mention", "message"}:
                text = str(event.get("text", ""))
                channel_id = str(event.get("channel", ""))
                log.info("slack_event_received", extra={"event": "slack_event", "text": text, "channel": channel_id})
                import re
                from domain import NormalizedEvent
                from queue.manager import ReviewJob
                clean_text = re.sub(r"<@.*?>", "", text)
                match = re.search(r"#?(\d+)", clean_text)
                if match:
                    pr_num = int(match.group(1))
                    target_repo = config.repo_config[0] if config.repo_config else None
                    owner_name = target_repo.owner if target_repo else self_account
                    repo_name = target_repo.repo if target_repo else ""
                    log.info(
                        "slack_command_parsed",
                        extra={
                            "event": "slack_command_parsed",
                            "pr": pr_num,
                            "owner": owner_name,
                            "repo": repo_name,
                            "command": text,
                        },
                    )
                    if "approve" in text.lower():
                        asyncio.create_task(slack.send_message(f"🚀 *Approved PR #{pr_num}!* Merging on GitHub...", channel=channel_id))
                        job = state.get_job(f"slack_{pr_num}") or ReviewJob(run_id=f"slack_{pr_num}", owner=owner_name, repo=repo_name, pr=pr_num, head="")
                        asyncio.create_task(pipeline.publish_approved_review(job, summary="Approved via Slack Event", findings=[], is_draft=True, auto_merge=True))
                    else:
                        asyncio.create_task(slack.send_message(f"👀 *Received review command for PR #{pr_num} (`{owner_name}/{repo_name}`)!* Initiating pipeline run...", channel=channel_id))
                        norm_event = NormalizedEvent(
                            event="issue_comment", action="created", owner=owner_name, repo=repo_name,
                            pr_number=pr_num, head_sha="", author=self_account, comment_body=text
                        )
                        asyncio.create_task(dispatcher.dispatch(norm_event))
        return {"status": "ok"}

    @app.post("/api/slack/interactivity")
    async def slack_interactivity(request: Request):
        """REQ-025: 2-Way Slack Block Kit Interactivity payload endpoint."""
        raw_body = (await request.body()).decode("utf-8")
        import urllib.parse
        parsed = urllib.parse.parse_qs(raw_body)
        payload_list = parsed.get("payload", [])
        if payload_list:
            payload_str = payload_list[0]
            import json
            from queue.manager import ReviewJob
            try:
                payload = json.loads(payload_str)
                if payload.get("type") == "block_actions":
                    actions = payload.get("actions", [])
                    if actions:
                        value = str(actions[0].get("value", ""))
                        log.info("slack_interactivity_action", extra={"action_value": value})
                        if value.startswith("approve_"):
                            run_id = value.replace("approve_", "")
                            job = state.get_job(run_id) or ReviewJob(run_id=run_id, owner=self_account, repo="", pr=1, head="")
                            asyncio.create_task(pipeline.publish_approved_review(job, summary="Approved via Slack Button", findings=[], is_draft=True, auto_merge=True))
            except Exception as exc:
                log.warning("failed to process Slack interactivity payload: %s", exc)
        return {"status": "ok"}

    @app.get("/healthz")
    async def healthz():
        """Liveness probe for the container healthcheck (no auth, no logging)."""
        return {"status": "ok"}

    @app.get("/status")
    async def get_status():
        """Provides real-time health, active workers, managed repos, and job metrics."""
        runs = state.reconcile_open_jobs()
        managed_repos = [f"{r.owner}/{r.repo}" for r in config.repo_config if r.enabled]
        return {
            "status": "healthy",
            "active_workers": worker.active_workers,
            "managed_repos": managed_repos,
            "open_jobs_count": len(runs),
            "open_jobs": [
                {
                    "run_id": j.run_id,
                    "repo": f"{j.owner}/{j.repo}",
                    "pr": j.pr,
                    "status": j.status,
                    "attempts": j.attempts,
                }
                for j in runs
            ],
        }

    async def _registrar_loop() -> None:
        """REQ-CN-001: self-heal the webhook URL on boot, then on a loop."""
        while True:
            await registrar.reconcile()
            await asyncio.sleep(config.reconcile_interval_seconds)

    @app.on_event("startup")
    async def startup() -> None:
        queue.reconcile(lease_ttl_seconds=0)  # ARCH-011 boot sweep: recover interrupted running jobs immediately
        app.state.worker_task = asyncio.create_task(worker.run())
        app.state.registrar_task = asyncio.create_task(_registrar_loop())
        asyncio.create_task(backfill.run())

    @app.on_event("shutdown")
    async def shutdown() -> None:
        for name in ("worker_task", "registrar_task"):
            task = getattr(app.state, name, None)
            if task is not None:
                task.cancel()
        state.close()

    return app


def _secret_provider(config):
    async def secret() -> str:
        return os.environ.get(config.webhook_secret_env, "")

    return secret
