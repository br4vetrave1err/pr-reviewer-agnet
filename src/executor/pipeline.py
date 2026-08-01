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

    async def execute(self, job: ReviewJob, token: str) -> PipelineResult:
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

    async def _publish(self, job: ReviewJob, summary: str, findings: list[Finding]) -> None:
        inline = [
            {"path": f.path, "line": f.line or 1, "body": f"[{f.severity.value}] {f.title}\n{f.detail}"}
            for f in findings
            if f.path
        ]
        await self._github.submit_review(
            job.owner, job.repo, job.pr, job.head, summary, inline, job.run_id
        )


@dataclass
class PrContextSafe:
    diff_files: list[str] = field(default_factory=list)
    title: str = ""
    body: str = ""
