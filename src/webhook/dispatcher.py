# Implements: MOD-001, ARCH-001, SYS-001, REQ-001
"""Webhook dispatcher (MOD-001).

Routes a signature-validated, normalized event to the trigger filter and the
queue manager asynchronously (non-blocking dispatch, ACK < 2s). Skipped and
reply decisions are logged; only `enqueue` and `advance-ci` reach the queue.
"""

from __future__ import annotations

import asyncio
import logging

from domain import Decision, NormalizedEvent

log = logging.getLogger("pr_reviewer.webhook.dispatcher")


class Dispatcher:
    def __init__(self, trigger, queue_manager, reply_post=None):
        self._trigger = trigger
        self._queue = queue_manager
        self._reply_post = reply_post  # async callable(Decision) -> None

    async def dispatch(self, event: NormalizedEvent) -> None:
        try:
            decision: Decision = self._trigger.decide(event)
        except Exception:
            log.exception("trigger decision failed for %s/%s", event.owner, event.repo)
            return

        log.info("decision=%s reason=%s for %s/%s#%s", decision.action, decision.reason,
                 event.owner, event.repo, event.pr_number)

        if decision.action in {"enqueue", "advance-ci"}:
            self._queue.enqueue(decision, cause="webhook")
        elif decision.action in {"reply", "notify-merged"}:
            if self._reply_post is not None:
                await self._reply_post(decision)
            else:
                log.info("reply/notify decision dropped: no poster configured")
