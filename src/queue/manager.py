# Implements: MOD-004, ARCH-003, SYS-003, REQ-004, REQ-010, REQ-014, REQ-NF-005, REQ-NF-006
"""Queue Manager (MOD-004 / SYS-003).

Enqueues review jobs with transactional dedup (REQ-004 / REQ-NF-005), kicks
off the CI-gate wait, and drives the run state machine. Concurrency is 1
(REQ-NF-006). Retry with backoff and the reconcile sweep live here too.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional

from domain import Decision, GateResult

log = logging.getLogger("pr_reviewer.queue.manager")

PENDING_CI = "pending_ci"
QUEUED = "queued"
RUNNING = "running"
POSTED = "posted"
FAILED = "failed"
PARTIAL = "partial"
SKIPPED = "skipped"
CI_FAILED = "ci-failed"


@dataclass
class ReviewJob:
    owner: str
    repo: str
    pr: int
    head: str
    model: Optional[str] = None
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    attempts: int = 0
    status: str = PENDING_CI
    ci_status: Optional[str] = None
    cause: str = "webhook"
    run_config: Optional[dict] = None


@dataclass
class EnqueueResult:
    run_id: str
    duplicate: bool = False
    reason: str = ""


class QueueManager:
    """Serial FIFO job queue (concurrency 1)."""

    def __init__(self, state, ci_gate, max_attempts: int = 3):
        self._state = state
        self._ci_gate = ci_gate
        self._max_attempts = max_attempts
        self._queue: asyncio.Queue[ReviewJob] = asyncio.Queue()
        self._waker = asyncio.Event()
        self._queued: set[str] = set()  # run_ids currently in the in-memory queue

    def enqueue(self, decision: Decision, cause: str = "webhook") -> EnqueueResult:
        job = ReviewJob(
            owner=decision.owner,
            repo=decision.repo,
            pr=decision.pr,
            head=decision.head,
            model=decision.model,
            cause=cause,
        )
        inserted = self._state.insert_run(job)  # INSERT OR IGNORE dedup (REQ-004)
        if not inserted:
            log.info("coalesced duplicate job %s/%s#%s", job.owner, job.repo, job.pr)
            return EnqueueResult(run_id=job.run_id, duplicate=True, reason="dedup")

        self._ci_gate.watch(job)  # begin pending_ci wait (MOD-009)
        self._queued.add(job.run_id)
        self._queue.put_nowait(job)
        self._waker.set()
        log.info("enqueued run %s (%s/%s#%s)", job.run_id, job.owner, job.repo, job.pr)
        return EnqueueResult(run_id=job.run_id)

    def put_back(self, job: ReviewJob) -> None:
        """Re-enqueue a gate-passed job; idempotent per run_id (ARCH-011)."""
        if job.run_id in self._queued:
            return
        self._queued.add(job.run_id)
        self._queue.put_nowait(job)
        self._waker.set()

    async def dequeue(self) -> Optional[ReviewJob]:
        while True:
            if not self._queue.empty():
                job = self._queue.get_nowait()
                self._queued.discard(job.run_id)
                if self._state.claim_run(job.run_id):  # running in tx
                    return job
                continue  # lost the claim; try next
            self._waker.clear()
            try:
                await asyncio.wait_for(self._waker.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                return None

    def reconcile(self, lease_ttl_seconds: int = 3600) -> int:
        """Boot sweep: requeue orphans and resume pending CI (ARCH-011)."""
        count = self._state.recover_orphans(lease_ttl_seconds)
        for job in self._state.reconcile_open_jobs():
            if job.status == PENDING_CI:
                self._ci_gate.watch(job)  # resume the CI wait (ARCH-011)
            self._queued.add(job.run_id)
            self._queue.put_nowait(job)
        return count
