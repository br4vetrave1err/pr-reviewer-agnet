# Implements: ITP-004-A, ARCH-004, REQ-005
"""ITP-004-A: eviction frees space when the cache is at its disk cap."""

import os
import subprocess

import pytest

from cache.clone import CachedRepo, CloneCacheManager

from tests.integration.conftest import state


class _FakeProc:
    returncode = 0
    stdout = ""
    stderr = ""


class FakeState:
    def __init__(self, repos, cache_root):
        self._repos = repos
        self._root = cache_root

    def get_repo(self, key):
        return self._repos.get(key)

    def put_repo(self, entry):
        self._repos[entry.owner + "/" + entry.repo] = entry

    def touch_repo(self, key, ts):
        self._repos[key].last_used = ts

    def list_repos(self):
        return sorted(self._repos.values(), key=lambda r: r.last_used)

    def remove_repo(self, key):
        self._repos.pop(key, None)


@pytest.mark.asyncio
async def test_its_004_a2_eviction_frees_space_at_disk_cap(tmp_path, monkeypatch):
    cache_root = tmp_path / "cache"
    repo_a = cache_root / "acme" / "app-a"
    repo_b = cache_root / "acme" / "app-b"
    repo_a.mkdir(parents=True)
    repo_b.mkdir(parents=True)
    (repo_a / "blob").write_bytes(b"x" * 600)  # 600 bytes each
    (repo_b / "blob").write_bytes(b"x" * 600)

    fake_state = FakeState(
        {
            "acme/app-a": CachedRepo("acme", "app-a", str(repo_a), 100),
            "acme/app-b": CachedRepo("acme", "app-b", str(repo_b), 200),
        },
        cache_root,
    )

    git_calls = []
    real_run = subprocess.run

    def fake_run(cmd, **kw):
        if cmd and cmd[0] == "git" and cmd[1] == "clone":
            os.makedirs(cmd[-1], exist_ok=True)
            (Path(cmd[-1]) / "blob").write_bytes(b"x" * 600)
        if cmd and cmd[0] == "git":
            git_calls.append(cmd)
            return _FakeProc()
        return real_run(cmd, **kw)

    monkeypatch.setattr(subprocess, "run", fake_run)

    from pathlib import Path

    cap = 1000  # only one repo fits; cloning a third must evict an LRU
    clone = CloneCacheManager(str(cache_root), fake_state, disk_cap_bytes=cap)
    clone.ensure("acme", "app-c", "sha3", "tok")

    # the LRU (app-a, last_used=100) was evicted; new clone succeeded
    assert "acme/app-a" not in fake_state._repos
    assert (cache_root / "acme" / "app-c").exists()
    assert any(c[1] == "clone" for c in git_calls)
