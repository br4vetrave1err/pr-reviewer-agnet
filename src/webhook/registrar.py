# Implements: REQ-CN-001
"""Webhook registrar (REQ-CN-001).

Self-heals the GitHub webhook URL against the ngrok tunnel's current public
URL. Discovers the live tunnel from the ngrok agent's local API, then ensures
every managed repo has a webhook pointing at ``<tunnel>/api/webhook`` with the
correct secret — creating it when missing, re-pointing it when the tunnel URL
changes (free tier assigns a new subdomain per restart). Runs at boot and on a
reconcile loop so the public URL never needs manual updating.
"""

from __future__ import annotations

import logging

import httpx

from config.load import Config
from github.client import GitHubClient
from webhook.handler import SUPPORTED_EVENTS

log = logging.getLogger("pr_reviewer.webhook.registrar")

_NGROK_TUNNELS_API = "/api/tunnels"
_WEBHOOK_PATH = "/api/webhook"


class WebhookRegistrar:
    def __init__(
        self,
        config: Config,
        github: GitHubClient,
        secret: str,
        ngrok_agent_url: str = "http://ngrok:4040",
        webhook_path: str = _WEBHOOK_PATH,
        httpx_client: httpx.AsyncClient | None = None,
    ):
        self._config = config
        self._github = github
        self._secret = secret
        self._ngrok_agent = ngrok_agent_url.rstrip("/")
        self._webhook_path = webhook_path
        self._client = httpx_client or httpx.AsyncClient()

    async def tunnel_public_url(self) -> str:
        """Return the app tunnel's current public HTTPS URL (REQ-CN-001, REQ-024)."""
        import os
        env_url = os.environ.get("PUBLIC_AGENT_URL") or os.environ.get("NGROK_PUBLIC_URL")
        if env_url:
            return env_url.rstrip("/")
        resp = await self._client.get(f"{self._ngrok_agent}{_NGROK_TUNNELS_API}")
        resp.raise_for_status()
        tunnels = resp.json().get("tunnels", [])
        https = [t for t in tunnels if t.get("proto") == "https" and t.get("public_url")]
        if not https:
            raise RuntimeError("no active ngrok tunnel")
        return https[0]["public_url"].rstrip("/")

    async def reconcile(self) -> int:
        """Ensure all managed repos' webhooks point at the tunnel URL.

        Returns the number of webhooks created or re-pointed. Never raises:
        failures are logged so the loop keeps self-healing.
        """
        try:
            tunnel = await self.tunnel_public_url()
            log.info("ngrok_url_acquired", extra={"event": "ngrok_url_acquired", "public_url": tunnel})
        except Exception as exc:
            log.warning(
                "ngrok_error",
                extra={"event": "ngrok_error", "error": str(exc), "will_retry": True},
            )
            return 0
        desired = f"{tunnel.rstrip('/')}{self._webhook_path}"
        changed = 0
        for repo in self._config.repo_config:
            if not repo.enabled:
                continue
            try:
                if await self._ensure(repo.owner, repo.repo, desired):
                    changed += 1
            except Exception as exc:
                log.warning("webhook reconcile failed for %s/%s: %s", repo.owner, repo.repo, exc)
        if changed:
            log.info(
                "ngrok_reconcile",
                extra={
                    "event": "ngrok_reconcile",
                    "webhook_updated": changed,
                    "target_url": desired,
                },
            )
        return changed

    async def _ensure(self, owner: str, repo: str, desired_url: str) -> bool:
        """Point the repo's app webhook at *desired_url*; True if changed."""
        hooks = await self._github.list_webhooks(owner, repo)
        hook = next(
            (
                h
                for h in hooks
                if str((h.get("config") or {}).get("url", "")).rstrip("/").endswith(self._webhook_path)
            ),
            None,
        )
        if hook is None:
            created = await self._github.create_webhook(owner, repo, desired_url, self._secret, set(SUPPORTED_EVENTS))
            log.info("created webhook %s for %s/%s -> %s", created.get("id"), owner, repo, desired_url)
            return True
        current = str((hook.get("config") or {}).get("url", "")).rstrip("/")
        if current == desired_url.rstrip("/"):
            return False
        await self._github.update_webhook(owner, repo, int(hook["id"]), url=desired_url, secret=self._secret)
        log.info("re-pointed webhook %s for %s/%s -> %s", hook["id"], owner, repo, desired_url)
        return True
