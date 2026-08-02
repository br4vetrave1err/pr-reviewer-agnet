# Implements: REQ-025, ATP-025-A, SCN-025-A1, SCN-025-A2
"""Unit tests for 2-Way Slack Events & Interactivity routes (REQ-025)."""

import pytest
from fastapi.testclient import TestClient
from webhook.app import create_app
from config.load import Config, RepoSpec


@pytest.fixture
def test_config():
    return Config(repo_config=[RepoSpec(owner="testowner", repo="testrepo")])


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "test.db"))
    return TestClient(app)


def test_slack_url_verification(client):
    """SCN-025-A1: Test URL verification challenge token response."""
    payload = {
        "type": "url_verification",
        "token": "J24bE5...",
        "challenge": "3eZbrw1aXaZCRrTOvStructure...",
    }
    resp = client.post("/api/slack/events", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"challenge": "3eZbrw1aXaZCRrTOvStructure..."}


def test_slack_event_app_mention(client):
    """SCN-025-A2: Test app_mention event callback parsing."""
    payload = {
        "type": "event_callback",
        "event": {
            "type": "app_mention",
            "text": "<@U123456> review #1",
            "channel": "C123456",
        },
    }
    resp = client.post("/api/slack/events", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_slack_interactivity_button_click(client):
    """Test Block Kit interactivity form-encoded payload processing."""
    payload_json = (
        '{"type": "block_actions", "actions": [{"value": "approve_run123"}]}'
    )
    resp = client.post(
        "/api/slack/interactivity",
        data={"payload": payload_json},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200


def test_slack_event_explicit_repo_command(client):
    """Test app_mention event callback parsing with explicit repo name."""
    payload = {
        "type": "event_callback",
        "event": {
            "type": "app_mention",
            "text": "<@U123456> review developer-roadmap #1",
            "channel": "C123456",
        },
    }
    resp = client.post("/api/slack/events", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_slack_interactivity_select_repo_click(client):
    """Test repo selection Block Kit button click processing."""
    payload_json = (
        '{"type": "block_actions", "actions": [{"value": "select_repo_br4vetrave1err/developer-roadmap_1"}]}'
    )
    resp = client.post(
        "/api/slack/interactivity",
        data={"payload": payload_json},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200


def test_slack_event_no_pr_number(client):
    """Test app_mention without a PR number returns usage hint."""
    payload = {
        "type": "event_callback",
        "event": {
            "type": "app_mention",
            "text": "<@U123456> can you raise a new PR with some test changes",
            "channel": "C123456",
        },
    }
    resp = client.post("/api/slack/events", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

