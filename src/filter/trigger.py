# Implements: MOD-002, ARCH-002, SYS-002, REQ-002, REQ-003, REQ-013
"""Trigger Decision Engine (MOD-002 / SYS-002).

Decides whether an incoming event warrants a review: self-account authored
(`opened`/`ready_for_review`/`synchronize` — ATP-004-A re-review on new head),
requested reviewer, or a self `@review` comment
(REQ-002). Applies ``repo_config`` management (REQ-003) and the denylist;
skips everything else with a logged reason.
"""

from __future__ import annotations

import logging

from config.load import Config
from domain import Command, Decision, NormalizedEvent
from filter.command import CommandSyntaxError, parse_command

log = logging.getLogger("pr_reviewer.filter.trigger")


class TriggerDecisionEngine:
    def __init__(self, config: Config, self_account: str):
        self._config = config
        self._self_account = self_account

    def decide(self, event: NormalizedEvent) -> Decision:
        d = self._decide_inner(event)
        log.info(
            "trigger_decision",
            extra={
                "event": "trigger_decision",
                "action": d.action,
                "owner": d.owner,
                "repo": d.repo,
                "pr": d.pr,
                "head": d.head,
                "reason": d.reason,
            },
        )
        return d

    def _decide_inner(self, event: NormalizedEvent) -> Decision:
        if event.event == "issue_comment":
            if self._self_account and event.author != self._self_account:
                return Decision(action="skip", reason="not-self")
            try:
                cmd = parse_command(event.comment_body or "")
            except CommandSyntaxError:
                return Decision(action="reply", reason="malformed-command")
            if cmd is None:
                return Decision(action="skip", reason="not-command")
            return Decision(
                action="reply",
                owner=event.owner,
                repo=event.repo,
                pr=event.pr_number,
                head=event.head_sha,
                model=cmd.model,
                target=cmd,
            )

        if event.event in {"check_run", "workflow_run"} and event.action == "completed":
            return Decision(
                action="advance-ci",
                owner=event.owner,
                repo=event.repo,
                pr=event.pr_number,
                head=event.head_sha,
                target=Command(kind="advance-ci", model=None),
            )

        if event.event == "pull_request" and (event.action == "closed" or event.pr_state in {"closed", "merged"}):
            if event.pr_state == "merged" or event.action == "closed":
                return Decision(
                    action="notify-merged",
                    owner=event.owner,
                    repo=event.repo,
                    pr=event.pr_number,
                    head=event.head_sha,
                )
            return Decision(action="skip", reason="not-open")

        if event.draft and self._self_account and event.author != self._self_account:
            return Decision(action="skip", reason="draft-not-self")  # REQ-018

        if self._self_account:
            is_author = event.author == self._self_account and event.action in {
                "opened",
                "ready_for_review",
                "synchronize",
            }
            is_reviewer = event.action == "review_requested" and self._self_account in event.requested_reviewers
            if not (is_author or is_reviewer):
                return Decision(action="skip", reason="not-self")

        if not self._config.is_managed(event.owner, event.repo):
            return Decision(action="skip", reason="not-managed")  # REQ-003

        if self._config.is_denied(event.owner, event.repo):
            return Decision(action="skip", reason="denied")

        return Decision(
            action="enqueue",
            owner=event.owner,
            repo=event.repo,
            pr=event.pr_number,
            head=event.head_sha,
        )
