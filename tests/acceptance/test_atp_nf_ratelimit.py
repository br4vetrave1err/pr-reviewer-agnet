# Implements: ATP-NF-003-A
"""ATP-NF-003-A: GitHub rate-limit backoff and retry.

User journey: a GitHub API call returning 403/429 backs off with jitter and
retries rather than failing immediately.
"""

import asyncio

import httpx
import pytest
from github.client import GitHubClient, RateLimitError


@pytest.mark.asyncio
async def test_scn_nf_003_a1_429_backs_off_and_retries():
    from unittest.mock import patch

    calls = {"n": 0}

    def fake_schedule_retry(attempt, category):
        return 0.0  # no real sleep in the test

    class FakeTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            calls["n"] += 1
            if calls["n"] < 3:
                return httpx.Response(429, headers={"Retry-After": "1"}, json={"message": "rate limited"})
            return httpx.Response(200, json={"id": 42})

    client = GitHubClient(token="t", httpx_client=httpx.AsyncClient(transport=FakeTransport()))

    with patch("github.client.schedule_retry", side_effect=fake_schedule_retry):
        review_id = await client.submit_review("acme", "app", 1, "abc123", "ok", [], "run-1")

    assert calls["n"] == 3  # retried after 429, not failed immediately
    assert review_id == 42


@pytest.mark.asyncio
async def test_scn_nf_003_a1_403_rate_limit_eventually_raises():
    from unittest.mock import patch

    class FakeTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return httpx.Response(403, headers={"Retry-After": "1"}, json={"message": "rate limited"})

    client = GitHubClient(token="t", httpx_client=httpx.AsyncClient(transport=FakeTransport()))

    with patch("github.client.schedule_retry", side_effect=lambda a, c: 0.0):
        try:
            await client.post_comment("acme", "app", 1, "hi")
            raise AssertionError("expected RateLimitError")
        except RateLimitError:
            pass  # backoff exhausted -> surfaced, never a crash
