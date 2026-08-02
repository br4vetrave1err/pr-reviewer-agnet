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

        app_url = approval_url or f"http://localhost:8000/api/reviews/{run_id}/approve"
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
                        {"type": "mrkdwn", "text": f"*Repository:*\n<{pr_link}|{owner}/{repo}#{pr}>"},
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
                        }
                    ],
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Or comment `@review approve` directly on PR #{pr} to release this review.",
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
