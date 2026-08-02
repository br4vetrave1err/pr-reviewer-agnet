# Implements: MOD-013, ARCH-009, SYS-009, REQ-011, REQ-012, REQ-NF-003, REQ-NF-001, REQ-IF-001
"""GitHub Client (MOD-013 / SYS-009).

Submits formal reviews (event ``COMMENT`` always, REQ-012) with the
idempotency marker and inline comments, fetches CI check runs/job logs, and
posts comments. Retries 403/429 with backoff (REQ-NF-003). 404 -> resource
gone -> skip. PAT read from ``GITHUB_TOKEN`` env (never logged).
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from observability.ratelimit import schedule_retry

log = logging.getLogger("pr_reviewer.github.client")

_GITHUB_API = "https://api.github.com"


class NotFoundError(Exception):
    """GitHub 404 — the resource (PR) is gone (ARCH-009)."""


class RateLimitError(Exception):
    """GitHub 403/429 — rate limited; carries the Retry-After hint."""

    def __init__(self, message: str = "", retry_after: Optional[float] = None):
        super().__init__(message or "GitHub rate limited")
        self.retry_after = retry_after


class MalformedDataError(Exception):
    """Response payload missing expected fields (ARCH-009)."""


@dataclass
class CheckRun:
    name: str
    status: str
    conclusion: Optional[str]
    completed: bool = False
    failed: bool = False


class GitHubClient:
    def __init__(self, token: Optional[str] = None, base_url: str = _GITHUB_API, httpx_client: Optional[httpx.AsyncClient] = None):
        self._token = token or os.environ.get("GITHUB_TOKEN", "")
        self._base = base_url
        self._client = httpx_client or httpx.AsyncClient()

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def submit_review(
        self,
        owner: str,
        repo: str,
        pr: int,
        head: str,
        summary: str,
        inline_comments: list[dict],
        run_id: str,
        event: str = "COMMENT",
    ) -> int:
        """REQ-012, REQ-022: submit review event (COMMENT or APPROVE) with idempotency marker."""
        marker = f"\n\n<!-- review-run:{run_id} -->"
        payload = {
            "commit_id": head,
            "event": event,
            "body": summary + marker,  # REQ-IF-001 idempotency
            "comments": inline_comments,
        }
        url = f"{self._base}/repos/{owner}/{repo}/pulls/{pr}/reviews"
        try:
            data = await self._retryable(lambda: self._client.post(url, json=payload, headers=self._headers()))
            if isinstance(data, dict) and "id" in data:
                return int(data["id"])
        except Exception as exc:
            log.warning("submit_review with inline comments failed for %s/%s#%s: %s; trying summary only", owner, repo, pr, exc)
            if inline_comments:
                payload_no_inline = {
                    "commit_id": head,
                    "event": event,
                    "body": summary + marker,
                }
                try:
                    data = await self._retryable(lambda: self._client.post(url, json=payload_no_inline, headers=self._headers()))
                    if isinstance(data, dict) and "id" in data:
                        return int(data["id"])
                except Exception:
                    pass
            await self.post_comment(owner, repo, pr, summary + marker)
            return 0
        return 0

    async def mark_pr_ready_for_review(self, owner: str, repo: str, pr: int) -> bool:
        """REQ-022: Mark/convert a draft PR to ready for review via GitHub API."""
        url = f"{self._base}/repos/{owner}/{repo}/pulls/{pr}"
        try:
            resp = await self._client.patch(
                url, json={"draft": False}, headers=self._headers()
            )
            if resp.status_code in (200, 201):
                log.info("marked_pr_ready_for_review", extra={"owner": owner, "repo": repo, "pr": pr})
                return True
        except Exception as exc:
            log.warning("failed to mark PR %s/%s#%s ready for review: %s", owner, repo, pr, exc)
        return False

    async def merge_pr(self, owner: str, repo: str, pr: int, merge_method: str = "squash") -> bool:
        """REQ-022: Auto-merge approved Pull Request on GitHub with fallback merge methods."""
        url = f"{self._base}/repos/{owner}/{repo}/pulls/{pr}/merge"
        methods = list(dict.fromkeys([merge_method, "squash", "merge", "rebase"]))
        for method in methods:
            payload = {
                "commit_title": f"Merge pull request #{pr} via PR Review Agent",
                "merge_method": method,
            }
            try:
                resp = await self._client.put(url, json=payload, headers=self._headers())
                if resp.status_code == 200:
                    log.info("merged_pr_successfully", extra={"owner": owner, "repo": repo, "pr": pr, "method": method})
                    return True
                log.warning("merge_pr with method %s returned HTTP %s: %s", method, resp.status_code, resp.text)
            except Exception as exc:
                log.warning("failed to merge PR %s/%s#%s with method %s: %s", owner, repo, pr, method, exc)
        return False

    async def fetch_pr_head(self, owner: str, repo: str, pr: int) -> str:
        url = f"{self._base}/repos/{owner}/{repo}/pulls/{pr}"
        data = await self._retryable(lambda: self._client.get(url, headers=self._headers()))
        if isinstance(data, dict):
            return (data.get("head") or {}).get("sha") or ""
        return ""

    async def fetch_pr_diff(self, owner: str, repo: str, pr: int) -> str:
        url = f"{self._base}/repos/{owner}/{repo}/pulls/{pr}"
        resp = await self._client.get(
            url,
            headers={**self._headers(), "Accept": "application/vnd.github.diff"},
        )
        if resp.status_code == 404:
            raise NotFoundError(f"PR not found (HTTP 404)")
        if resp.status_code == 200:
            return resp.text
        if resp.status_code in (403, 429):
            raise RateLimitError(retry_after=_parse_retry_after(resp.headers.get("Retry-After")))
        resp.raise_for_status()
        return ""

    async def post_comment(self, owner: str, repo: str, pr: int, body: str) -> None:
        url = f"{self._base}/repos/{owner}/{repo}/issues/{pr}/comments"
        await self._retryable(lambda: self._client.post(url, json={"body": body}, headers=self._headers()))

    async def poll_check_runs(self, owner: str, repo: str, head: str) -> list[CheckRun]:
        url = f"{self._base}/repos/{owner}/{repo}/commits/{head}/check-runs"
        data = await self._retryable(lambda: self._client.get(url, headers=self._headers()))
        runs = []
        for r in (data or {}).get("check_runs", []):
            conclusion = r.get("conclusion")
            runs.append(
                CheckRun(
                    name=r.get("name", ""),
                    status=r.get("status", ""),
                    conclusion=conclusion,
                    completed=r.get("status") == "completed",
                    failed=bool(conclusion and conclusion != "success"),
                )
            )
        return runs

    async def fetch_failure_logs(self, owner: str, repo: str, pr: int, head: str) -> str:
        runs = await self.poll_check_runs(owner, repo, head)
        chunks: list[str] = []
        for r in runs:
            if not r.failed:
                continue
            url = f"{self._base}/repos/{owner}/{repo}/commits/{head}/check-runs/{r.name}/annotations"
            try:
                data = await self._retryable(lambda: self._client.get(url, headers=self._headers()))
                chunks.append(f"[{r.name}]\n" + "\n".join(a.get("message", "") for a in (data or [])[:50]))
            except Exception:
                log.warning("log fetch failed for %s", r.name)
        return "\n".join(chunks)

    async def fetch_pr(self, owner: str, repo: str, pr: int) -> dict:
        url = f"{self._base}/repos/{owner}/{repo}/pulls/{pr}"
        data = await self._retryable(lambda: self._client.get(url, headers=self._headers()))
        if not isinstance(data, dict) or "number" not in data:
            raise MalformedDataError(f"malformed PR payload for {owner}/{repo}#{pr}")
        return data

    async def list_webhooks(self, owner: str, repo: str) -> list[dict]:
        """REQ-CN-001: list the repo's registered webhooks."""
        url = f"{self._base}/repos/{owner}/{repo}/hooks"
        data = await self._retryable(lambda: self._client.get(url, headers=self._headers()))
        if not isinstance(data, list):
            raise MalformedDataError(f"webhook list returned malformed payload for {owner}/{repo}")
        return data

    async def list_open_prs(self, owner: str, repo: str) -> list[dict]:
        """REQ-002: list open pull requests for a repository (boot backfill)."""
        url = f"{self._base}/repos/{owner}/{repo}/pulls?state=open"
        data = await self._retryable(lambda: self._client.get(url, headers=self._headers()))
        if not isinstance(data, list):
            return []
        return data

    async def create_webhook(self, owner: str, repo: str, url: str, secret: str, events: set[str]) -> dict:
        """REQ-CN-001: register a webhook pointing at *url* for the managed repo."""
        endpoint = f"{self._base}/repos/{owner}/{repo}/hooks"
        payload = {
            "name": "web",
            "active": True,
            "events": list(events),
            "config": {
                "url": url,
                "content_type": "json",
                "insecure_ssl": "0",
                "secret": secret,
            },
        }
        data = await self._retryable(lambda: self._client.post(endpoint, json=payload, headers=self._headers()))
        if not isinstance(data, dict) or "id" not in data:
            raise MalformedDataError(f"webhook create returned malformed payload for {owner}/{repo}")
        return data

    async def update_webhook(self, owner: str, repo: str, hook_id: int, url: str, secret: str) -> dict:
        """REQ-CN-001: re-point an existing webhook at a new URL.

        GitHub replaces unspecified config fields on PATCH, so the secret must
        be re-sent or the HMAC is silently dropped (deliveries -> 401).
        """
        endpoint = f"{self._base}/repos/{owner}/{repo}/hooks/{hook_id}"
        payload = {
            "config": {
                "url": url,
                "content_type": "json",
                "insecure_ssl": "0",
                "secret": secret,
            }
        }
        data = await self._retryable(lambda: self._client.patch(endpoint, json=payload, headers=self._headers()))
        if not isinstance(data, dict) or "id" not in data:
            raise MalformedDataError(f"webhook update returned malformed payload for {owner}/{repo}")
        return data

    async def _retryable(self, call) -> Any:
        import time
        attempt = 1
        while True:
            t0 = time.monotonic()
            resp = await call()
            latency_ms = int((time.monotonic() - t0) * 1000)
            log.info(
                "github_request",
                extra={
                    "event": "github_request",
                    "method": str(resp.request.method if hasattr(resp, "request") and resp.request else "HTTP"),
                    "url_path": str(resp.url.path if hasattr(resp, "url") and resp.url else ""),
                    "status": resp.status_code,
                    "latency_ms": latency_ms,
                    "attempt": attempt,
                },
            )
            if resp.status_code in (200, 201):
                return resp.json() if resp.content else {}
            if resp.status_code == 404:
                raise NotFoundError(f"resource not found (HTTP 404)")
            if resp.status_code in (403, 429) and attempt < 5:
                retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
                delay = retry_after or schedule_retry(attempt, "github")
                log.warning(
                    "github_rate_limited",
                    extra={
                        "event": "github_rate_limited",
                        "status": resp.status_code,
                        "retry_after_s": delay,
                        "attempt": attempt,
                    },
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue
            if resp.status_code in (403, 429):
                raise RateLimitError(retry_after=retry_after or schedule_retry(attempt, "github"))
            resp.raise_for_status()
            return None


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    try:
        return float(value) if value else None
    except (TypeError, ValueError):
        return None
