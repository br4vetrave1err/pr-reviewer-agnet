# Implements: MOD-009, ARCH-003, SYS-008, REQ-010
"""CI Gate Monitor (MOD-009).

Runs while a job is ``pending_ci``. No CI for the head after the settle
window -> bypass to ``queued``. All runs complete -> green -> ``queued``;
any failed -> ``ci-failed`` and a diagnosis comment (Rule B). Hitting the
wait cap (60 min) -> ``skipped`` with one explanatory comment.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from domain import GateResult
from queue.manager import PENDING_CI, QUEUED, CI_FAILED, SKIPPED, ReviewJob

log = logging.getLogger("pr_reviewer.ci.gate")


class CiGateMonitor:
    def __init__(
        self,
        github,
        state,
        settle_seconds: int = 75,
        wait_cap_minutes: int = 60,
        poll_interval_seconds: int = 30,
    ):
        self._github = github
        self._state = state
        self._settle = settle_seconds
        self._cap = wait_cap_minutes * 60
        self._poll = poll_interval_seconds
        self._requeue = None  # set by attach(); re-enqueues jobs on gate pass

    def attach(self, queue) -> None:
        """Wire the queue so a passed gate re-enqueues the job (ARCH-011)."""
        self._requeue = queue.put_back

    async def resolve_gate(self, head: str, elapsed_seconds: float) -> GateResult:
        """UTP-009-A: resolve the gate for a head (no-ci / green / red / timeout)."""
        try:
            runs = await self._github.poll_check_runs("", "", head)
        except Exception:
            runs = []

        if not runs:
            if elapsed_seconds >= self._settle:
                return GateResult(passed=True, reason="no-ci", ci_status="none")
            return GateResult(passed=False, reason="pending", ci_status="none")

        completed = all(r.completed for r in runs)
        failed = any(r.failed for r in runs)
        if completed and failed:
            return GateResult(passed=False, reason="ci-failed", ci_status="failed")
        if completed:
            return GateResult(passed=True, reason="green", ci_status="success")
        if elapsed_seconds >= self._cap:
            return GateResult(passed=False, reason="timeout", ci_status="pending")
        return GateResult(passed=False, reason="pending", ci_status="pending")

    def watch(self, job: ReviewJob) -> None:
        """Kick off the async CI wait; returns immediately (non-blocking)."""
        asyncio.create_task(self._watch(job))

    async def _watch(self, job: ReviewJob) -> None:
        elapsed = 0.0
        while self._state.get_run(job.run_id).status == PENDING_CI:
            try:
                if not job.head:
                    runs = []
                else:
                    runs = await self._github.poll_check_runs(job.owner, job.repo, job.head)
            except Exception:  # poll API 403/429 -> backoff, stay pending (ARCH-009)
                log.warning("CI poll failed for %s; staying pending_ci", job.run_id)
                await asyncio.sleep(self._poll)
                elapsed += self._poll
                continue

            if not runs:
                self._state.set_status(job.run_id, QUEUED)  # no-CI bypass
                self._pass(job)
                log.info(
                    "ci_gate_resolved",
                    extra={
                        "event": "ci_gate_resolved",
                        "run_id": job.run_id,
                        "outcome": "no_ci_bypass",
                        "duration_ms": int(elapsed * 1000),
                    },
                )
                return

            log.info(
                "ci_gate_waiting",
                extra={
                    "event": "ci_gate_waiting",
                    "run_id": job.run_id,
                    "owner": job.owner,
                    "repo": job.repo,
                    "pr": job.pr,
                    "head": job.head,
                    "pending_checks": len([r for r in runs if not r.completed]),
                },
            )

            if all(r.completed for r in runs):
                if any(r.failed for r in runs):
                    await self._fail(job, elapsed)
                else:
                    self._state.set_status(job.run_id, QUEUED)  # green -> review proceeds
                    self._pass(job)
                    log.info(
                        "ci_gate_resolved",
                        extra={
                            "event": "ci_gate_resolved",
                            "run_id": job.run_id,
                            "outcome": "green",
                            "duration_ms": int(elapsed * 1000),
                        },
                    )
                return

            if elapsed >= self._cap:
                self._state.set_status(job.run_id, SKIPPED)
                await self._github.post_comment(
                    job.owner, job.repo, job.pr, "CI hasn't completed; no review run"
                )
                log.info(
                    "ci_gate_resolved",
                    extra={
                        "event": "ci_gate_resolved",
                        "run_id": job.run_id,
                        "outcome": "timeout_skipped",
                        "duration_ms": int(elapsed * 1000),
                    },
                )
                return

            await asyncio.sleep(self._poll)
            elapsed += self._poll

            if all(r.completed for r in runs):
                if any(r.failed for r in runs):
                    await self._fail(job)
                else:
                    self._state.set_status(job.run_id, QUEUED)  # green -> review proceeds
                    self._pass(job)
                return

            if elapsed >= self._cap:
                self._state.set_status(job.run_id, SKIPPED)
                await self._github.post_comment(
                    job.owner, job.repo, job.pr, "CI hasn't completed; no review run"
                )
                log.info("CI wait cap reached; skipped %s", job.run_id)
                return

    def _pass(self, job: ReviewJob) -> None:
        """Job passed the gate; put it back on the queue for the worker."""
        if self._requeue is not None:
            self._requeue(job)

    async def _fail(self, job: ReviewJob, elapsed: float = 0.0) -> None:
        self._state.set_status(job.run_id, CI_FAILED)
        try:
            logs = await self._github.fetch_failure_logs(job.owner, job.repo, job.pr, job.head)
            diagnosis = self._diagnose(logs)
            await self._github.post_comment(job.owner, job.repo, job.pr, diagnosis)
        except Exception:
            await self._github.post_comment(
                job.owner, job.repo, job.pr,
                "CI failed for this head; logs were unavailable during diagnosis.",
            )
        log.info(
            "ci_gate_resolved",
            extra={
                "event": "ci_gate_resolved",
                "run_id": job.run_id,
                "outcome": "ci_failed",
                "duration_ms": int(elapsed * 1000),
            },
        )

    def _diagnose(self, logs: str) -> str:
        """Root-cause pass on CI logs (/diagnosing-bugs context)."""
        if not logs:
            return "CI failed for this head; logs were unavailable."
        tail = logs[-2000:]
        return (
            "**CI gate failed.**\n"
            "Root-cause notes from the failure logs:\n```\n"
            f"{tail}\n```\n"
            "This review run will not proceed until CI is green."
        )
