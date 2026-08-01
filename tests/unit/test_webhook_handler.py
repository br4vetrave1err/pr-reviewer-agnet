# Implements: UTP-001-A, UTS-001-A1, UTS-001-A2, MOD-001, ARCH-001, REQ-001
"""Unit tests — MOD-001 (Webhook Handler)."""

import hashlib
import hmac
import json

import pytest

from webhook.handler import (
    SUPPORTED_ACTIONS,
    SignatureError,
    WebhookHandler,
    normalize_event,
    parse_webhook,
    verify_hmac,
)

SECRET = "s3cret"
PAYLOAD = json.dumps({"action": "opened", "pull_request": {"number": 7, "head": {"sha": "abc"}}, "repository": {"name": "r", "owner": {"login": "o"}}}).encode()


def _sig(secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), PAYLOAD, hashlib.sha256).hexdigest()


def test_uts_001_a1_valid_signature_returns_typed_event():
    event = parse_webhook(SECRET, PAYLOAD, "pull_request", _sig())
    assert event.event == "pull_request"
    assert event.pr_number == 7
    assert event.head_sha == "abc"


def test_uts_001_a2_missing_signature_raises():
    with pytest.raises(SignatureError):
        parse_webhook(SECRET, PAYLOAD, "pull_request", None)


def test_uts_001_a2_mismatched_signature_raises():
    with pytest.raises(SignatureError):
        parse_webhook(SECRET, PAYLOAD, "pull_request", "sha256=" + "0" * 64)


def test_verify_hmac_bad_sig_constant_time_false():
    assert verify_hmac(SECRET, PAYLOAD, "sha256=" + "f" * 64) is False


def test_unsupported_action_gated():
    assert "opened" in SUPPORTED_ACTIONS["pull_request"]
    assert "deleted" not in SUPPORTED_ACTIONS["pull_request"]


def test_normalize_pr_state_merged():
    payload = json.loads(PAYLOAD)
    payload["pull_request"]["merged"] = True
    ev = normalize_event("pull_request", "synchronize", payload)
    assert ev.pr_state == "merged"
