# Implements: REQ-019, MOD-017, ARCH-013, SYS-014
"""Slack Block Kit Webhook Notifier (REQ-019 / MOD-017).

Sends a Slack Block Kit formatted notification containing the review summary
preview, finding counts, run ID, and approval action links to the configured
`SLACK_WEBHOOK_URL` when a review reaches `pending_approval`.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

log = logging.getLogger("pr_reviewer.observability.slack")


class SlackNotifier:
    def __init__(self, webhook_url: Optional[str] = None, httpx_client: Optional[httpx.AsyncClient] = None):
        self._webhook_url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL", "")
        self._client = httpx_client or httpx.AsyncClient()

    def _base_url(self) -> str:
        return (
            os.environ.get("PUBLIC_AGENT_URL")
            or os.environ.get("NGROK_PUBLIC_URL")
            or "http://localhost:8000"
        ).rstrip("/")

    async def notify_staged_review(
        self,
        run_id: str,
        owner: str,
        repo: str,
        pr: int,
        head: str,
        summary: str,
        findings_count: int,
        approval_url: Optional[str] = None,
    ) -> bool:
        """Send Slack Block Kit preview message for a pending_approval review (REQ-019)."""
        if not self._webhook_url:
            log.warning("SLACK_WEBHOOK_URL not configured; skipping Slack preview notification for %s", run_id)
            return False

        app_url = approval_url or f"{self._base_url()}/api/reviews/{run_id}/approve?owner={owner}&repo={repo}&pr={pr}"
        pr_link = f"https://github.com/{owner}/{repo}/pull/{pr}"

        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"🔍 PR Review Staged Preview: {owner}/{repo}#{pr}",
                        "emoji": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*PR Link:*\n<{pr_link}|{owner}/{repo}#{pr}>"},
                        {"type": "mrkdwn", "text": f"*Head Commit:*\n`{head[:7] if head else 'N/A'}`"},
                        {"type": "mrkdwn", "text": f"*Total Findings:*\n`{findings_count}`"},
                        {"type": "mrkdwn", "text": f"*Run ID:*\n`{run_id}`"},
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Review Summary Preview:*\n>{summary[:300]}...",
                    },
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Approve & Post to GitHub", "emoji": True},
                            "style": "primary",
                            "url": app_url,
                            "value": f"approve_{run_id}",
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Open PR on GitHub ↗", "emoji": True},
                            "url": pr_link,
                            "value": f"open_pr_{pr}",
                        },
                    ],
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Or comment `@review approve` directly on <{pr_link}|PR #{pr}> to release this review.",
                        }
                    ],
                },
            ]
        }

        try:
            resp = await self._client.post(self._webhook_url, json=payload, timeout=10.0)
            if resp.status_code == 200:
                log.info("slack_notification_sent", extra={"event": "slack_notification_sent", "run_id": run_id})
                return True
            log.warning("slack notification HTTP %s: %s", resp.status_code, resp.text)
        except Exception as exc:
            log.warning("failed to send Slack notification for %s: %s", run_id, exc)

        return False

    async def notify_review_approved_and_promoted(
        self,
        run_id: str,
        owner: str,
        repo: str,
        pr: int,
        is_draft: bool = True,
        merged: bool = False,
    ) -> bool:
        """Send Slack confirmation message when a PR review is approved, promoted, and merged on GitHub (REQ-022)."""
        if not self._webhook_url:
            return False

        pr_link = f"https://github.com/{owner}/{repo}/pull/{pr}"
        if merged:
            title = "🚀 PR Approved & Merged Successfully!"
            status_text = f"• *Review Status:* Approved (`event: APPROVE`)\n• *PR Status:* *Merged into base branch* 🎉"
        elif is_draft:
            title = "✅ PR Approved & Promoted to Ready for Review!"
            status_text = f"• *Review Status:* Approved (`event: APPROVE`)\n• *Draft Status:* Promoted to *Ready for Review* on GitHub 🎉"
        else:
            title = "✅ PR Review Approved & Published!"
            status_text = f"• *Review Status:* Approved & Published (`event: APPROVE`)"

        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": title,
                        "emoji": True,
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"The review for <{pr_link}|*{owner}/{repo}#{pr}*> has been processed.\n{status_text}",
                    },
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View PR on GitHub ↗", "emoji": True},
                            "style": "primary",
                            "url": pr_link,
                            "value": f"view_pr_{pr}",
                        }
                    ],
                },
            ]
        }

        try:
            resp = await self._client.post(self._webhook_url, json=payload, timeout=10.0)
            return resp.status_code == 200
        except Exception as exc:
            log.warning("failed to send Slack approval confirmation for %s: %s", run_id, exc)
            return False
