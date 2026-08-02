# Implements: MOD-004, ARCH-003, SYS-003, REQ-002, REQ-004
"""Boot Backfill Sweep."""

from __future__ import annotations

import logging

from domain import NormalizedEvent

log = logging.getLogger("pr_reviewer.queue.backfill")


class BootBackfill:
    def __init__(self, config, github, trigger, dispatcher, state):
        self._config = config
        self._github = github
        self._trigger = trigger
        self._dispatcher = dispatcher
        self._state = state

    async def run(self) -> int:
        enqueued_count = 0
        for repo_cfg in self._config.repo_config:
            if not repo_cfg.enabled:
                continue
            owner = repo_cfg.owner
            repo = repo_cfg.repo
            try:
                prs = await self._github.list_open_prs(owner, repo)
            except Exception as exc:
                log.warning("boot backfill list_open_prs failed for %s/p%s: %s", owner, repo, exc)
                continue

            for pr_data in prs:
                if not isinstance(pr_data, dict):
                    continue
                pr_number = pr_data.get("number")
                head = (pr_data.get("head") or {}).get("sha")
                author = (pr_data.get("user") or {}).get("login")
                requested_reviewers = [
                    (u.get("login") or "") for u in (pr_data.get("requested_reviewers") or [])
                ]
                state_str = pr_data.get("state")

                if not (pr_number and head):
                    continue

                if self._state.has_run_for_head(owner, repo, pr_number, head):
                    continue

                event = NormalizedEvent(
                    event="pull_request",
                    action="opened",
                    owner=owner,
                    repo=repo,
                    pr_number=pr_number,
                    head_sha=head,
                    author=author,
                    requested_reviewers=requested_reviewers,
                    pr_state=state_str,
                )
                decision = self._trigger.decide(event)
                if decision.action == "enqueue":
                    log.info(
                        "boot_backfill_enqueue",
                        extra={
                            "event": "boot_backfill_enqueue",
                            "owner": owner,
                            "repo": repo,
                            "pr": pr_number,
                            "head": head,
                        },
                    )
                    await self._dispatcher.dispatch(event)
                    enqueued_count += 1

        if enqueued_count:
            log.info("boot_backfill_completed", extra={"event": "boot_backfill_completed", "enqueued": enqueued_count})
        return enqueued_count
