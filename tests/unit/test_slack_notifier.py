# Implements: UTP-019, REQ-019, MOD-017, ARCH-013, SYS-014
"""Unit tests for Slack Block Kit Webhook Notifier (REQ-019)."""

import pytest
import httpx
from observability.slack_notifier import SlackNotifier


@pytest.mark.asyncio
async def test_slack_notifier_sends_block_kit_payload():
    requests = []

    async def mock_handler(request: httpx.Request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)

    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/services/test/webhook", httpx_client=client)

    success = await notifier.notify_staged_review(
        run_id="run_123",
        owner="br4vetrave1err",
        repo="developer-roadmap",
        pr=5,
        head="sha12345",
        summary="No security issues found.",
        findings_count=2,
    )

    assert success is True
    assert len(requests) == 1
    assert "hooks.slack.com" in str(requests[0].url)
    assert b"PR Review Staged Preview" in requests[0].content
