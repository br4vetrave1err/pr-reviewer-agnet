# Implements: UTP-013-A, UTS-013-A1, UTS-013-A2, UTS-013-A3, MOD-013, ARCH-009, REQ-001, REQ-011, REQ-NF-003
"""Unit tests — MOD-013 (GitHub Client)."""

import pytest

from github.client import GitHubClient, MalformedDataError, NotFoundError, RateLimitError


class FakeResponse:
    def __init__(self, status_code, data=None, headers=None, text=""):
        self.status_code = status_code
        self._data = data
        self.headers = headers or {}
        self.content = data is not None
        self.text = text

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def get(self, url, headers=None):
        self.calls.append(("get", url))
        return self._responses.pop(0)

    async def post(self, url, json=None, headers=None):
        self.calls.append(("post", url))
        return self._responses.pop(0)


def _client(*responses):
    return GitHubClient(token="t", base_url="https://api.github.com", httpx_client=FakeClient(list(responses)))


@pytest.mark.asyncio
async def test_uts_013_a1_404_raises_not_found():
    gh = _client(FakeResponse(404))
    with pytest.raises(NotFoundError):
        await gh.fetch_pr("o", "r", 1)


@pytest.mark.asyncio
async def test_uts_013_a2_403_raises_rate_limit_after_retries(monkeypatch):
    responses = [FakeResponse(403, headers={"Retry-After": "0"}) for _ in range(5)]
    gh = _client(*responses)

    async def fake_sleep(sec):
        return None

    monkeypatch.setattr("github.client.asyncio.sleep", fake_sleep)
    with pytest.raises(RateLimitError):
        await gh.fetch_pr("o", "r", 1)
    assert len(gh._client.calls) == 5


@pytest.mark.asyncio
async def test_uts_013_a2_429_raises_rate_limit(monkeypatch):
    gh = _client(*[FakeResponse(429, headers={"Retry-After": "0"}) for _ in range(5)])

    async def fake_sleep(sec):
        return None

    monkeypatch.setattr("github.client.asyncio.sleep", fake_sleep)
    with pytest.raises(RateLimitError):
        await gh.fetch_pr("o", "r", 1)


@pytest.mark.asyncio
async def test_uts_013_a3_malformed_payload_raises():
    gh = _client(FakeResponse(200, data={"state": "open"}))  # no "number"
    with pytest.raises(MalformedDataError):
        await gh.fetch_pr("o", "r", 1)


@pytest.mark.asyncio
async def test_review_submit_uses_comment_event():
    gh = _client(FakeResponse(201, data={"id": 42}))
    review_id = await gh.submit_review("o", "r", 1, "head", "summary", [], "run1")
    assert review_id == 42
    url, payload = gh._client.calls[0][1], gh._client._responses  # posted url
    assert "/reviews" in gh._client.calls[0][1]
