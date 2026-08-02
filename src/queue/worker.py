# Implements: MOD-005, ARCH-003, SYS-003, REQ-004, REQ-010, REQ-014, REQ-NF-005, REQ-NF-006
"""Worker Scheduler (MOD-005 / ARCH-003).

Claims queued jobs (status -> running, transactionally), runs the pipeline
(MOD-006..MOD-012), and applies the retry/partial/posted state outcomes
(REQ-014). Runs up to ``concurrency`` workers (default 1, REQ-NF-006).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from queue.manager import ReviewJob

log = logging.getLogger("pr_reviewer.queue.worker")


class WorkerScheduler:
    def __init__(
        self,
        manager,
        pipeline: Callable[[ReviewJob], object],
        max_attempts: int = 3,
        concurrency: int = 1,
        idle_backoff_seconds: float = 5.0,
    ):
        self._manager = manager
        self._pipeline = pipeline
        self._max_attempts = max_attempts
        self._concurrency = concurrency
        self._idle_backoff = idle_backoff_seconds
        self._active = 0

    @property
    def active_workers(self) -> int:
        return self._active

    async def run(self) -> None:
        """Spawn the worker loop(s) — at most ``concurrency`` active (REQ-NF-006)."""
        workers = [asyncio.create_task(self._worker_loop()) for _ in range(self._concurrency)]
        await asyncio.gather(*workers)

    async def dispatch(self, jobs: list[ReviewJob]) -> None:
        """UTP-005-A: enqueue a batch, run workers until drained."""
        for job in jobs:
            self._manager._queue.put_nowait(job)
        self._manager._waker.set()

    async def _worker_loop(self) -> None:
        while True:
            job = await self._manager.dequeue()
            if job is None:
                await asyncio.sleep(self._idle_backoff)
                continue

            self._active += 1
            import time
            t0 = time.monotonic()
            log.info(
                "job_started",
                extra={
                    "event": "job_started",
                    "run_id": job.run_id,
                    "attempt": job.attempts + 1,
                },
            )
            try:
                result = await self._pipeline(job)
                if result is None:
                    continue

                if result.retryable and job.attempts < self._max_attempts:
                    job.attempts += 1
                    self._manager._state.set_status(job.run_id, "queued")  # retry (REQ-014)
                    self._manager._queue.put_nowait(job)
                    log.info("retrying run %s attempt %d/%d", job.run_id, job.attempts, self._max_attempts)
                elif result.retryable:
                    self._manager._state.set_status(job.run_id, "failed")
                    log.warning("run %s failed after %d attempts; posting partial", job.run_id, self._max_attempts)
                    slack = getattr(self._manager, "_slack", None)
                    if slack:
                        await slack.notify_review_failed(job.run_id, job.owner, job.repo, job.pr, f"Retries exhausted ({self._max_attempts} attempts)")
                else:
                    self._manager._state.set_status(job.run_id, result.status or "posted")
            except Exception as exc:
                self._manager._state.set_status(job.run_id, "failed")
                log.error("unhandled exception in run %s: %s", job.run_id, exc)
                slack = getattr(self._manager, "_slack", None)
                if slack:
                    await slack.notify_review_failed(job.run_id, job.owner, job.repo, job.pr, str(exc))
            finally:
                self._active -= 1
                duration_ms = int((time.monotonic() - t0) * 1000)
                log.info(
                    "job_completed",
                    extra={
                        "event": "job_completed",
                        "run_id": job.run_id,
                        "duration_ms": duration_ms,
                    },
                )
