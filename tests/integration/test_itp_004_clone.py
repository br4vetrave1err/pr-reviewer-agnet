# Implements: ITP-004-A, ARCH-004, REQ-005
"""ITP-004-A: workers share the clone cache; second run reuses the clone."""

import os
import subprocess

import pytest

from cache.clone import CloneCacheManager

from tests.integration.conftest import state


class _FakeProc:
    returncode = 0
    stdout = ""
    stderr = ""


@pytest.mark.asyncio
async def test_its_004_a1_two_runs_share_cached_clone(tmp_path, monkeypatch, state):
    git_calls = []
    real_run = subprocess.run

    def fake_run(cmd, **kw):
        if cmd and cmd[0] == "git" and cmd[1] == "clone":
            os.makedirs(cmd[-1], exist_ok=True)
        if cmd and cmd[0] == "git":
            git_calls.append(cmd)
            return _FakeProc()
        return real_run(cmd, **kw)

    monkeypatch.setattr(subprocess, "run", fake_run)

    clone = CloneCacheManager(str(tmp_path / "cache"), state, disk_cap_bytes=2 ** 30)

    first = clone.ensure("acme", "app", "abc123", "tok")
    second = clone.ensure("acme", "app", "def456", "tok")

    assert first == second  # same physical checkout, no duplicated clone
    clones = [c for c in git_calls if c[1] == "clone"]
    fetches = [c for c in git_calls if "fetch" in c[1:]]
    assert len(clones) == 1  # clone happened exactly once
    assert len(fetches) == 1  # second run only fetched to the new head
