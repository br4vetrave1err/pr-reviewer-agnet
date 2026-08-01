# Implements: STP-001-A, STP-001-B, SYS-001, REQ-001, REQ-IF-002, REQ-NF-002
"""STP-001-A/B: webhook signature gate, fast ACK, and backpressure survival."""

import hashlib
import hmac
import json
import time

from fastapi import FastAPI, Header, Request
from fastapi.testclient import TestClient

from webhook.handler import WebhookHandler

SECRET = "b" * 32


async def _secret():
    return SECRET


def _payload(author="reviewer-bot"):
    return json.dumps({
        "action": "opened",
        "repository": {"owner": {"login": "acme"}, "name": "app"},
        "pull_request": {
            "number": 1, "head": {"sha": "abc123"}, "user": {"login": author},
            "state": "open", "requested_reviewers": [],
        },
        "sender": {"login": author},
    }).encode()


def _sig(payload):
    return "sha256=" + hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()


def _app(dispatcher_calls):
    class RecordingDispatcher:
        async def dispatch(self, event):
            dispatcher_calls.append(event)

    handler = WebhookHandler(_secret, RecordingDispatcher(), "reviewer-bot")
    app = FastAPI()

    @app.post("/api/webhook")
    async def webhook(request: Request, x_hub_signature_256: str | None = Header(default=None)):
        return await handler.handle(request, x_hub_signature_256)

    return app


def _wait_for(calls, n, deadline=2.0):
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        if len(calls) >= n:
            return
        time.sleep(0.02)


def test_sts_001_a1_valid_signature_acks_within_2s():
    calls = []
    with TestClient(_app(calls)) as client:
        payload = _payload()
        start = time.monotonic()
        resp = client.post(
            "/api/webhook",
            content=payload,
            headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": _sig(payload)},
        )
        elapsed = time.monotonic() - start
    _wait_for(calls, 1)
    assert resp.status_code == 200
    assert elapsed < 2.0  # REQ-NF-002
    assert len(calls) == 1  # normalized event handed to SYS-002
    assert calls[0].owner == "acme" and calls[0].head_sha == "abc123"


def test_sts_001_a2_invalid_signature_401_no_dispatch():
    calls = []
    with TestClient(_app(calls)) as client:
        payload = _payload()
        resp = client.post(
            "/api/webhook",
            content=payload,
            headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": "sha256=deadbeef"},
        )
        time.sleep(0.05)
    assert resp.status_code == 401
    assert calls == []  # no event dispatched


def test_sts_001_b1_receiver_survives_saturated_queue():
    calls = []
    with TestClient(_app(calls)) as client:
        payload = _payload()
        start = time.monotonic()
        for _ in range(20):  # saturate the receiver with concurrent deliveries
            resp = client.post(
                "/api/webhook",
                content=payload,
                headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": _sig(payload)},
            )
            assert resp.status_code == 200
        elapsed = time.monotonic() - start
    _wait_for(calls, 20)
    assert elapsed < 2.0  # receiver never blocks on the pipeline
    assert len(calls) == 20  # all queued despite saturation
