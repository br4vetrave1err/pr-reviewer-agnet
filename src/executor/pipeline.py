# Implements: MOD-006, MOD-007, MOD-008, MOD-009, MOD-010, MOD-011, MOD-012, MOD-013, ARCH-003, SYS-003
"""Review pipeline (MOD-006..MOD-012 orchestration).

Executes one claimed job through clone -> docs -> workspace run -> compliance
-> security -> report -> publish, returning the final run status for the
worker scheduler (MOD-005).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from domain import Finding, ReviewResult
from queue.manager import ReviewJob
from runner.workspace import PromptContext

log = logging.getLogger("pr_reviewer.executor.pipeline")


@dataclass
class PipelineResult:
    status: str = "posted"
    retryable: bool = False


class ReviewPipeline:
    def __init__(
        self,
        clone_cache,
        docs_loader,
        workspace_runner,
        compliance_validator,
        security_scanner,
        llm_reviewer,
        github_client,
        skills_selector,
        config,
        slack_notifier=None,
    ):
        self._clone = clone_cache
        self._docs = docs_loader
        self._runner = workspace_runner
        self._compliance = compliance_validator
        self._scanner = security_scanner
        self._llm = llm_reviewer
        self._github = github_client
        self._skills = skills_selector
        self._config = config
        self._slack = slack_notifier
        self._staged_reviews: dict[str, tuple[str, list[Finding]]] = {}

    async def execute(self, job: ReviewJob, token: str) -> PipelineResult:
        if not job.head and job.pr:
            try:
                job.head = await self._github.fetch_pr_head(job.owner, job.repo, job.pr)
            except Exception as exc:
                log.warning("failed to fetch head SHA for PR %s/%s#%s: %s", job.owner, job.repo, job.pr, exc)

        try:
            checkout = self._clone.ensure(job.owner, job.repo, job.head, token)
        except Exception as exc:
            log.warning("clone failed for %s: %s", job.run_id, exc)
            return PipelineResult(retryable=True)  # ARCH-004; retried then partial

        docs = self._docs.load(job.owner, job.repo)  # MOD-007; degrades

        try:
            diff = await self._fetch_diff(job)
        except Exception as exc:
            log.warning("diff fetch failed for %s: %s", job.run_id, exc)
            return PipelineResult(retryable=True)

        model_alias = job.model or self._config.default_model
        result = await self._runner.run(
            checkout,
            PromptContext(
                head=job.head,
                owner=job.owner,
                repo=job.repo,
                pr=job.pr,
                docs_text="\n\n".join(docs.content.values()),
                diff=diff,
                model_alias=model_alias,
                auth_ref=self._auth_ref(model_alias),
                skill_args=self._skills.select([]),
            ),
        )

        if result.retryable:
            return PipelineResult(retryable=True)  # REQ-014

        findings = self._assemble_findings(checkout, result, diff)

        # REQ-019, REQ-020: Send Slack preview notification and hold in pending_approval
        if self._slack:
            self._staged_reviews[job.run_id] = (result.summary, findings)
            await self._slack.notify_staged_review(
                run_id=job.run_id,
                owner=job.owner,
                repo=job.repo,
                pr=job.pr,
                head=job.head,
                summary=result.summary,
                findings_count=len(findings),
            )
            log.info("staged_review_pending_approval", extra={"event": "staged_review_pending_approval", "run_id": job.run_id})
            return PipelineResult(status="pending_approval")

        # Fallback: if no Slack notifier configured, publish directly
        await self._publish(job, result.summary, findings)
        return PipelineResult(status="posted")

    async def _fetch_diff(self, job: ReviewJob) -> str:
        return await self._github.fetch_pr_diff(job.owner, job.repo, job.pr)

    def _auth_ref(self, model_alias: str) -> str:
        return self._config.providers[model_alias].auth_env or "OPENCODE_GO_TOKEN"

    def _assemble_findings(self, checkout: str, result: ReviewResult, diff: str) -> list[Finding]:
        findings = list(result.findings)

        sec = self._scanner.scan(checkout)  # MOD-011; never aborts
        findings.extend(sec.secrets)

        compliance = self._compliance.validate(PrContextSafe(diff_files=[]))
        findings.extend(self._compliance.to_findings(compliance))

        return findings[: 100]

    async def publish_approved_review(self, job: ReviewJob, summary: str = "", findings: list[Finding] | None = None, is_draft: bool = True, auto_merge: bool = True) -> None:
        """REQ-021, REQ-022: Publish approved review, promote Draft PRs, and auto-merge PR on GitHub."""
        if job.run_id in self._staged_reviews:
            summary, findings = self._staged_reviews.pop(job.run_id)
        elif not summary and (findings is None):
            summary = "Approved via Slack"
            findings = []

        event = "APPROVE" if is_draft else "COMMENT"
        await self._publish(job, summary, findings or [], event=event)
        if is_draft:
            await self._github.mark_pr_ready_for_review(job.owner, job.repo, job.pr)  # REQ-022
        merged = False
        if auto_merge:
            merged = await self._github.merge_pr(job.owner, job.repo, job.pr)
        if self._slack:
            await self._slack.notify_review_approved_and_promoted(
                run_id=job.run_id, owner=job.owner, repo=job.repo, pr=job.pr, is_draft=is_draft, merged=merged
            )

    async def _publish(self, job: ReviewJob, summary: str, findings: list[Finding], event: str = "COMMENT") -> None:
        inline = [
            {"path": f.path, "line": f.line or 1, "body": f"[{f.severity.value}] {f.title}\n{f.detail}"}
            for f in findings
            if f.path
        ]
        await self._github.submit_review(
            job.owner, job.repo, job.pr, job.head, summary, inline, job.run_id, event=event
        )


@dataclass
class PrContextSafe:
    diff_files: list[str] = field(default_factory=list)
    title: str = ""
    body: str = ""
