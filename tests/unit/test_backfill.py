# Implements: MOD-004, ARCH-003, SYS-003, REQ-002, REQ-004
"""Unit tests for BootBackfill."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from queue.backfill import BootBackfill


@pytest.mark.asyncio
async def test_boot_backfill_skips_already_reviewed():
    config = MagicMock()
    repo_cfg = MagicMock()
    repo_cfg.enabled = True
    repo_cfg.owner = "owner"
    repo_cfg.repo = "repo"
    config.repo_config = [repo_cfg]

    github = AsyncMock()
    github.list_open_prs.return_value = [
        {"number": 1, "head": {"sha": "head123"}, "user": {"login": "author"}}
    ]

    trigger = MagicMock()
    dispatcher = AsyncMock()
    state = MagicMock()
    state.has_run_for_head.return_value = True

    backfill = BootBackfill(config, github, trigger, dispatcher, state)
    count = await backfill.run()

    assert count == 0
    dispatcher.dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_boot_backfill_enqueues_unreviewed():
    config = MagicMock()
    repo_cfg = MagicMock()
    repo_cfg.enabled = True
    repo_cfg.owner = "owner"
    repo_cfg.repo = "repo"
    config.repo_config = [repo_cfg]

    github = AsyncMock()
    github.list_open_prs.return_value = [
        {"number": 2, "head": {"sha": "head456"}, "user": {"login": "author"}}
    ]

    trigger = MagicMock()
    decision = MagicMock()
    decision.action = "enqueue"
    trigger.decide.return_value = decision

    dispatcher = AsyncMock()
    state = MagicMock()
    state.has_run_for_head.return_value = False

    backfill = BootBackfill(config, github, trigger, dispatcher, state)
    count = await backfill.run()

    assert count == 1
    dispatcher.dispatch.assert_called_once()
