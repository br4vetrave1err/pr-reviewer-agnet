# Implements: STP-004-A, SYS-004, REQ-005
"""STP-004-A: clone/update/evict cache lifecycle at the disk-cap boundary."""

import os
import subprocess

import pytest

from cache.clone import CachedRepo, CloneCacheManager

from tests.system.conftest import state


class _FakeProc:
    returncode = 0
    stdout = ""
    stderr = ""


class _FakeState:
    def __init__(self, repos=None, root=None):
        self._repos = repos or {}
        self._root = root

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


@pytest.fixture()
def git_calls(monkeypatch):
    calls = []
    real_run = subprocess.run

    def fake_run(cmd, **kw):
        if cmd and cmd[0] == "git" and cmd[1] == "clone":
            os.makedirs(cmd[-1], exist_ok=True)
        if cmd and cmd[0] == "git":
            calls.append(cmd)
            return _FakeProc()
        return real_run(cmd, **kw)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_sts_004_a1_first_ensure_full_clone(tmp_path, git_calls, state):
    clone = CloneCacheManager(str(tmp_path / "cache"), state, disk_cap_bytes=2 ** 30)
    path = clone.ensure("acme", "app", "abc123", "tok")
    assert (tmp_path / "cache" / "acme" / "app").is_dir()
    assert path == str(tmp_path / "cache" / "acme" / "app")
    assert any(c[1] == "clone" for c in git_calls)


def test_sts_004_a2_cached_clone_fetches_not_reclones(tmp_path, git_calls):
    fs = _FakeState(
        {"acme/app": CachedRepo("acme", "app", str(tmp_path / "cache" / "acme" / "app"), 1)}
    )
    clone = CloneCacheManager(str(tmp_path / "cache"), fs, disk_cap_bytes=2 ** 30)
    clone.ensure("acme", "app", "def456", "tok")
    assert not any(c[1] == "clone" for c in git_calls)  # updated via fetch only
    assert any("fetch" in c[1:] for c in git_calls)


def test_sts_004_a3_evicts_lru_until_under_cap(tmp_path, git_calls):
    cache_root = tmp_path / "cache"
    a = cache_root / "acme" / "a"
    b = cache_root / "acme" / "b"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    (a / "f").write_bytes(b"x" * 500)
    (b / "f").write_bytes(b"x" * 500)

    fs = _FakeState(
        {
            "acme/a": CachedRepo("acme", "a", str(a), 100),
            "acme/b": CachedRepo("acme", "b", str(b), 200),
        },
        cache_root,
    )
    clone = CloneCacheManager(str(cache_root), fs, disk_cap_bytes=800)
    clone.ensure("acme", "c", "sha", "tok")

    assert "acme/a" not in fs._repos  # LRU evicted
    assert (cache_root / "acme" / "c").exists()
