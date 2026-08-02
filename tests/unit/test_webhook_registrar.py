# Implements: UTP-CN-001-A, REQ-CN-001
"""Unit tests — webhook registrar self-healing (REQ-CN-001)."""

from config.load import Config, RepoSpec
from webhook.handler import SUPPORTED_EVENTS
from webhook.registrar import WebhookRegistrar


class FakeResp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeNgrok:
    def __init__(self, tunnels):
        self._tunnels = tunnels
        self.calls = []

    async def get(self, url, headers=None):
        self.calls.append(url)
        return FakeResp({"tunnels": self._tunnels})


class FakeGitHub:
    def __init__(self, hooks=None):
        self._hooks = list(hooks or [])
        self.created = []
        self.updated = []

    async def list_webhooks(self, owner, repo):
        return self._hooks

    async def create_webhook(self, owner, repo, url, secret, events):
        self.created.append((owner, repo, url, secret, sorted(events)))
        hook = {"id": 100 + len(self.created), "config": {"url": url}}
        self._hooks.append(hook)
        return hook

    async def update_webhook(self, owner, repo, hook_id, url, secret=None):
        self.updated.append((owner, repo, hook_id, url, secret))
        return {"id": hook_id, "config": {"url": url}}


def _config(*repos):
    entries = [RepoSpec(owner="acme", repo="app", enabled=True)] if not repos else list(repos)
    return Config(repo_config=entries)


def _https_tunnel(url="https://new.ngrok-free.app"):
    return FakeNgrok([{"proto": "https", "public_url": url}])


async def test_tunnel_public_url_returns_https():
    reg = WebhookRegistrar(_config(), FakeGitHub(), "secret", httpx_client=_https_tunnel())
    assert await reg.tunnel_public_url() == "https://new.ngrok-free.app"


async def test_reconcile_repoints_stale_hook():
    gh = FakeGitHub(hooks=[{"id": 7, "config": {"url": "https://old.ngrok-free.app/api/webhook"}}])
    reg = WebhookRegistrar(_config(), gh, "s3cret", httpx_client=_https_tunnel("https://new.ngrok-free.app"))

    assert await reg.reconcile() == 1
    assert gh.updated == [("acme", "app", 7, "https://new.ngrok-free.app/api/webhook", "s3cret")]
    assert gh.created == []


async def test_reconcile_noop_when_url_current():
    gh = FakeGitHub(hooks=[{"id": 7, "config": {"url": "https://new.ngrok-free.app/api/webhook"}}])
    reg = WebhookRegistrar(_config(), gh, "s3cret", httpx_client=_https_tunnel("https://new.ngrok-free.app"))

    assert await reg.reconcile() == 0
    assert gh.updated == []
    assert gh.created == []


async def test_reconcile_creates_missing_hook_with_secret_and_events():
    gh = FakeGitHub(hooks=[])
    reg = WebhookRegistrar(_config(), gh, "s3cret", httpx_client=_https_tunnel("https://new.ngrok-free.app"))

    assert await reg.reconcile() == 1
    assert len(gh.created) == 1
    owner, repo, url, secret, events = gh.created[0]
    assert (owner, repo, url, secret) == ("acme", "app", "https://new.ngrok-free.app/api/webhook", "s3cret")
    assert events == sorted(SUPPORTED_EVENTS)


async def test_reconcile_ignores_unrelated_webhooks():
    other = {"id": 1, "config": {"url": "https://elsewhere.dev/api/webhook/github"}}
    gh = FakeGitHub(hooks=[other])
    reg = WebhookRegistrar(_config(), gh, "s3cret", httpx_client=_https_tunnel("https://new.ngrok-free.app"))

    assert await reg.reconcile() == 1
    assert gh.updated == []
    assert gh.created[0][2] == "https://new.ngrok-free.app/api/webhook"


async def test_reconcile_skips_disabled_repo():
    disabled = RepoSpec(owner="acme", repo="quiet", enabled=False)
    gh = FakeGitHub(hooks=[])
    reg = WebhookRegistrar(_config(disabled), gh, "s3cret", httpx_client=_https_tunnel())

    assert await reg.reconcile() == 0
    assert gh.created == []


async def test_reconcile_noop_when_tunnel_down():
    reg = WebhookRegistrar(_config(), FakeGitHub(), "s3cret", httpx_client=FakeNgrok([]))
    assert await reg.reconcile() == 0
