# Implements: MOD-006, ARCH-004, SYS-004, REQ-005
"""Clone Cache Manager (MOD-006 / SYS-004).

Isolated per-repo clone workspace (``workspace_cache_dir``). Plain ``git
clone`` over HTTPS using the PAT on first use; incremental ``git fetch`` to
head afterwards; LRU eviction against the disk cap (REQ-005).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger("pr_reviewer.cache.clone")


@dataclass
class CachedRepo:
    owner: str
    repo: str
    path: str
    last_used: int


class CloneCacheManager:
    def __init__(self, cache_root: str | Path, state, disk_cap_bytes: int = 10 * 1024 * 1024 * 1024):
        self._cache_root = Path(cache_root)
        self._state = state
        self._disk_cap = disk_cap_bytes
        self._cache_root.mkdir(parents=True, exist_ok=True)

    def _repo_path(self, owner: str, repo: str) -> Path:
        return self._cache_root / owner / repo

    def ensure(self, owner: str, repo: str, head: str, token: str, remote_url: Optional[str] = None) -> str:
        """Return a checkout path for *head*, cloning/fetching as needed (REQ-005)."""
        key = f"{owner}/{repo}"
        entry = self._state.get_repo(key)
        path = self._repo_path(owner, repo)

        if entry is None:
            url = remote_url or f"https://x-access-token:{token}@github.com/{key}.git"
            self._git_clone(url, path)
            self._state.put_repo(CachedRepo(owner=owner, repo=repo, path=str(path), last_used=self._now()))
        else:
            self._git_fetch(path, head)
            self._state.touch_repo(key, self._now())

        self._evict_if_over_cap(path)
        return str(path)

    def _now(self) -> int:
        import time

        return int(time.time())

    def _git_clone(self, url: str, path: Path) -> None:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--filter=blob:none", url, str(path)],
            check=True,
            capture_output=True,
            text=True,
            env=self._git_env(),
        )

    def _git_fetch(self, path: Path, head: str) -> None:
        subprocess.run(
            ["git", "-C", str(path), "fetch", "origin", head],
            check=True,
            capture_output=True,
            text=True,
            env=self._git_env(),
        )

    @staticmethod
    def _git_env() -> dict:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        return env

    def _evict_if_over_cap(self, keep: Path) -> None:
        usage = sum(
            os.path.getsize(p) for p in self._cache_root.rglob("*") if p.is_file()
        )
        if usage <= self._disk_cap:
            return
        log.warning("disk cap exceeded (%d bytes); evicting LRU entries", usage)
        for entry in sorted(self._state.list_repos(), key=lambda r: r.last_used):
            if str(entry.path) == str(keep):
                continue
            shutil.rmtree(entry.path, ignore_errors=True)
            self._state.remove_repo(f"{entry.owner}/{entry.repo}")
            usage = sum(os.path.getsize(p) for p in self._cache_root.rglob("*") if p.is_file())
            if usage <= self._disk_cap:
                break
