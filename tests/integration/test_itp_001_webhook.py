# Implements: ITP-001-A, ARCH-001, REQ-001, REQ-IF-002, REQ-NF-002
"""ITP-001-A: webhook receiver wired to config secret and trigger filter."""

import json
import time

import pytest
from fastapi import FastAPI, Header, Request
from fastapi.testclient import TestClient

from config.load import validate as validate_config
from filter.trigger import TriggerDecisionEngine
from queue.manager import QueueManager
from state.db import StateRepository
from webhook.dispatcher import Dispatcher
from webhook.handler import WebhookHandler

from tests.integration.conftest import VALID_CONFIG_RAW, pull_request_payload, sign_payload

SECRET = "a" * 32


async def _secret():
    return SECRET


def build_app(self_account="reviewer-bot", trigger=None, queue=None):
    config = validate_config(dict(VALID_CONFIG_RAW))

    class FakeGate:
        def watch(self, job):
            pass

    if queue is None:
        queue = QueueManager(StateRepository(":memory:"), FakeGate())

    if trigger is None:
        trigger = TriggerDecisionEngine(config, self_account)

    dispatcher = Dispatcher(trigger, queue)
    handler = WebhookHandler(_secret, dispatcher, self_account)

    app = FastAPI()

    @app.post("/api/webhook")
    async def webhook(request: Request, x_hub_signature_256: str | None = Header(default=None)):
        return await handler.handle(request, x_hub_signature_256)

    return app, queue


def test_its_001_a1_signed_delivery_acks_fast(tmp_path):
    app, queue = build_app()
    state = queue._state
    with TestClient(app) as client:
        payload = json.dumps(pull_request_payload(author="reviewer-bot")).encode()
        start = time.monotonic()
        resp = client.post(
            "/api/webhook",
            content=payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": sign_payload(SECRET, payload),
            },
        )
        elapsed = time.monotonic() - start
        assert resp.status_code == 200
        assert elapsed < 2.0  # REQ-NF-002
        rows = _wait_for_jobs(state)
        assert len(rows) == 1
        assert rows[0].owner == "acme" and rows[0].head == "abc123"


def _wait_for_jobs(state, deadline: float = 2.0):
    import time as _t

    end = _t.monotonic() + deadline
    while _t.monotonic() < end:
        rows = state.reconcile_open_jobs()
        if rows:
            return rows
        _t.sleep(0.02)
    return []


def test_its_001_a2_unsigned_delivery_401_and_trigger_not_called():
    calls = []

    class SpyTrigger:
        def decide(self, event):
            calls.append(event)

    app, queue = build_app(trigger=SpyTrigger())
    with TestClient(app) as client:
        payload = json.dumps(pull_request_payload()).encode()
        resp = client.post(
            "/api/webhook",
            content=payload,
            headers={"X-GitHub-Event": "pull_request"},
        )
    assert resp.status_code == 401
    assert calls == []  # trigger filter never invoked
    assert len(queue._state.reconcile_open_jobs()) == 0
