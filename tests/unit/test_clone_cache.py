# Implements: UTP-006-A, UTS-006-A1, UTS-006-A2, UTS-006-A3, MOD-006, ARCH-004, REQ-005
"""Unit tests — MOD-006 (Clone Cache Manager)."""

import os
import subprocess

import pytest

from cache.clone import CachedRepo, CloneCacheManager
from state.db import StateRepository


class FakeState:
    def __init__(self, repos=None):
        self._repos = repos or {}

    def get_repo(self, key):
        return self._repos.get(key)

    def put_repo(self, entry):
        self._repos[entry.owner + "/" + entry.repo] = entry

    def touch_repo(self, key, ts):
        self._repos[key].last_used = ts

    def list_repos(self):
        return list(self._repos.values())

    def remove_repo(self, key):
        self._repos.pop(key, None)


@pytest.fixture()
def tmp_cache(tmp_path):
    return str(tmp_path / "cache")


def test_uts_006_a1_no_cache_full_clone(tmp_cache, monkeypatch):
    calls = []

    def fake_run(args, **kw):
        calls.append(args[1])
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    cm = CloneCacheManager(tmp_cache, FakeState())
    path = cm.ensure("acme", "app", "sha1", "tok")
    assert path.endswith(os.path.join("acme", "app"))
    assert calls.count("clone") == 1


def test_uts_006_a2_cached_clone_fetches_incremental(tmp_cache, monkeypatch):
    calls = []

    def fake_run(args, **kw):
        calls.append(" ".join(args))
        os.makedirs(os.path.join(tmp_cache, "acme", "app"), exist_ok=True)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = FakeState(repos={"acme/app": CachedRepo("acme", "app", os.path.join(tmp_cache, "acme", "app"), 1)})
    cm = CloneCacheManager(tmp_cache, state)
    cm.ensure("acme", "app", "sha2", "tok")
    assert "clone" not in calls  # no full re-clone
    assert any("fetch" in c for c in calls)


def test_uts_006_a3_evicts_lru_over_cap(tmp_cache, monkeypatch):
    def fake_run(args, **kw):
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    # Two repos: first used long ago (LRU), second recent.
    r1 = os.path.join(tmp_cache, "acme", "old")
    r2 = os.path.join(tmp_cache, "acme", "new")
    os.makedirs(r1)
    os.makedirs(r2)
    with open(os.path.join(r1, "f"), "wb") as fh:
        fh.write(b"x" * 5000)
    with open(os.path.join(r2, "f"), "wb") as fh:
        fh.write(b"y" * 5000)
    state = FakeState(
        repos={
            "acme/old": CachedRepo("acme", "old", r1, last_used=1),
            "acme/new": CachedRepo("acme", "new", r2, last_used=2),
        }
    )
    cm = CloneCacheManager(tmp_cache, state, disk_cap_bytes=6000)
    cm.ensure("acme", "new", "sha", "tok")
    assert not os.path.exists(r1)  # LRU evicted
    assert os.path.exists(r2)  # recently used kept
