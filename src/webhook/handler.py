# Implements: MOD-001, ARCH-001, SYS-001, REQ-001, REQ-NF-002, SYS-002
"""Webhook Handler (MOD-001 / SYS-001).

HTTPS endpoint ``POST /api/webhook``. Verifies the ``X-Hub-Signature-256``
HMAC before any work (REQ-001), gates on the supported event/action set,
normalizes the payload, and hands it to the dispatcher asynchronously so the
ACK returns within 2s (REQ-NF-002).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Optional

from fastapi import APIRouter, Header, Request, Response

from domain import NormalizedEvent

log = logging.getLogger("pr_reviewer.webhook")

SUPPORTED_EVENTS: frozenset[str] = frozenset(
    {"pull_request", "issue_comment", "check_run", "workflow_run"}
)

# Action filter per event (module-design MOD-001).
SUPPORTED_ACTIONS: dict[str, frozenset[str]] = {
    "pull_request": frozenset({"opened", "ready_for_review", "synchronize", "review_requested", "closed", "merged"}),
    "issue_comment": frozenset({"created"}),
    "check_run": frozenset({"completed"}),
    "workflow_run": frozenset({"completed"}),
}

router = APIRouter()


class SignatureError(Exception):
    """ARCH-001 `bad-signature`: HMAC mismatched or missing."""


def parse_webhook(secret: str, payload: bytes, event: str, signature: Optional[str]) -> NormalizedEvent:
    """Verify the HMAC then normalize (UTP-001-A). Raises SignatureError."""
    if not verify_hmac(secret, payload, signature):
        raise SignatureError("bad or missing X-Hub-Signature-256")
    body = json.loads(payload)
    action = str((body.get("action") or "") if isinstance(body, dict) else "")
    return normalize_event(event, action, body)


def verify_hmac(secret: str, payload: bytes, signature: Optional[str]) -> bool:
    """ARCH-001 `bad-signature`: constant-time HMAC-SHA256 comparison."""
    if not signature:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _parse_bool_or_state(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        return "merged" if value else "open"
    if isinstance(value, dict):
        state = value.get("state")
        merged = value.get("merged")
        if merged is True:
            return "merged"
        if state:
            return str(state)
    return str(value) if value else None


def normalize_event(event: str, action: str, payload: dict) -> NormalizedEvent:
    """Typed event for the dispatcher (MOD-001 normalization)."""
    pr = payload.get("pull_request") or {}
    repo = payload.get("repository") or {}
    sender = (payload.get("sender") or {}).get("login")
    if event == "pull_request":
        return NormalizedEvent(
            event=event,
            action=action,
            owner=(repo.get("owner") or {}).get("login") or "",
            repo=repo.get("name") or "",
            pr_number=pr.get("number"),
            head_sha=(pr.get("head") or {}).get("sha"),
            author=(pr.get("user") or {}).get("login"),
            requested_reviewers=[
                (u.get("login") or "") for u in (pr.get("requested_reviewers") or [])
            ],
            pr_state=_parse_bool_or_state(pr.get("state") or pr.get("merged")),
            sender=sender,
        )
    if event == "issue_comment":
        comment = payload.get("comment") or {}
        issue = payload.get("issue") or {}
        return NormalizedEvent(
            event=event,
            action=action,
            owner=(repo.get("owner") or {}).get("login") or "",
            repo=repo.get("name") or "",
            pr_number=issue.get("number") or pr.get("number"),
            head_sha=(pr.get("head") or {}).get("sha"),
            comment_body=comment.get("body"),
            author=(comment.get("user") or {}).get("login"),
            sender=sender,
        )
    # check_run / workflow_run
    return NormalizedEvent(
        event=event,
        action=action,
        owner=(repo.get("owner") or {}).get("login") or "",
        repo=repo.get("name") or "",
        pr_number=pr.get("number"),
        head_sha=(pr.get("head") or {}).get("sha"),
        ci_status=_ci_status(event, payload),
        sender=sender,
    )


def _ci_status(event: str, payload: dict) -> Optional[str]:
    if event == "check_run":
        check = payload.get("check_run") or {}
        conclusion = check.get("conclusion")
        status = check.get("status")
        if conclusion:
            return str(conclusion)
        return str(status) if status else None
    if event == "workflow_run":
        run = payload.get("workflow_run") or {}
        conclusion = run.get("conclusion")
        status = run.get("status")
        if conclusion:
            return str(conclusion)
        return str(status) if status else None
    return None


class WebhookHandler:
    def __init__(self, secret_provider, dispatcher, self_account: str = ""):
        self._secret = secret_provider
        self._dispatcher = dispatcher
        self._self_account = self_account

    async def handle(
        self,
        request: Request,
        x_hub_signature_256: Optional[str] = Header(default=None),
    ) -> Response:
        payload = await request.body()
        event = request.headers.get("x-github-event", "")
        try:
            body = json.loads(payload) if payload else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            log.warning("rejected webhook: malformed body")
            return Response(status_code=400)  # ARCH-001

        try:
            normalized = parse_webhook(await self._secret(), payload, event, x_hub_signature_256)
        except SignatureError as exc:
            log.info("rejected webhook: %s", exc)
            return Response(status_code=401)  # ARCH-001 bad-signature

        if event not in SUPPORTED_EVENTS or (body.get("action") or "") not in SUPPORTED_ACTIONS.get(event, frozenset()):
            log.info(
                "webhook_ignored",
                extra={
                    "event": "webhook_ignored",
                    "event_type": event,
                    "action": body.get("action"),
                    "reason": "unsupported_event_or_action",
                },
            )
            return Response(status_code=204)  # ignore silently

        asyncio.create_task(self._dispatcher.dispatch(normalized))
        log.info(
            "webhook_received",
            extra={
                "event": "webhook_received",
                "event_type": normalized.event,
                "action": normalized.action,
                "owner": normalized.owner,
                "repo": normalized.repo,
                "pr": normalized.pr_number,
                "sig_valid": True,
            },
        )
        return Response(status_code=200)
