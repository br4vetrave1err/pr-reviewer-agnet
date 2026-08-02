# Implements: MOD-015, ARCH-011, SYS-012, REQ-IF-005, REQ-NF-005, REQ-004, REQ-010, REQ-014, REQ-NF-001
"""State Repository (MOD-015 / SYS-012).

SQLite database with WAL journal (REQ-IF-005) implementing the documented
schema (``review_runs``, ``repos``, ``model_aliases``, ``repo_config``).
Transactional dedup (REQ-004 / REQ-NF-005), claim-in-tx, crash recovery via
orphan sweep, and the reconcile pass (REQ-010).
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

from cache.clone import CachedRepo
from queue.manager import ReviewJob

log = logging.getLogger("pr_reviewer.state.db")

_LEASE_TTL = 3600
_RUN_STATES = ("pending_ci", "queued", "running", "pending_approval", "posted", "failed", "partial", "skipped", "ci-failed")


class StateRepository:
    def __init__(self, db_path: str | Path, max_retries: int = 3):
        self._path = str(db_path)
        self._max_retries = max_retries
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, timeout=30, check_same_thread=False)
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")  # REQ-IF-005
        except sqlite3.OperationalError:
            self._conn.execute("PRAGMA journal_mode=DELETE")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._migrate()

    def _migrate(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS review_runs (
                run_id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                repo TEXT NOT NULL,
                pr INTEGER NOT NULL,
                head TEXT NOT NULL,
                model TEXT,
                status TEXT NOT NULL DEFAULT 'pending_ci',
                attempts INTEGER NOT NULL DEFAULT 0,
                cause TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE (owner, repo, pr, head, model)
            );
            CREATE TABLE IF NOT EXISTS repos (
                key TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                repo TEXT NOT NULL,
                path TEXT NOT NULL,
                last_used INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS model_aliases (
                alias TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS repo_config (
                owner TEXT NOT NULL,
                repo TEXT NOT NULL,
                default_model TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (owner, repo)
            );
            """
        )
        self._conn.commit()

    def get_job(self, run_id: str) -> Optional[ReviewJob]:
        """Fetch a ReviewJob by run_id from state database."""
        cur = self._conn.execute(
            "SELECT run_id, owner, repo, pr, head, model, status, attempts, cause FROM review_runs WHERE run_id=?",
            (run_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return ReviewJob(
            run_id=row[0], owner=row[1], repo=row[2], pr=row[3], head=row[4],
            model=row[5], status=row[6], attempts=row[7], cause=row[8]
        )

    # --- runs ---

    def insert_run(self, job: ReviewJob) -> bool:
        """INSERT OR IGNORE dedup (REQ-004); True if a row was inserted."""
        now = int(time.time())
        if job.cause == "comment":
            self._conn.execute(
                "DELETE FROM review_runs WHERE owner = ? AND repo = ? AND pr = ?",
                (job.owner, job.repo, job.pr),
            )
        try:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO review_runs "
                "(run_id, owner, repo, pr, head, model, status, attempts, cause, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (job.run_id, job.owner, job.repo, job.pr, job.head or "", job.model or "",
                 job.status, job.attempts, job.cause, now, now),
            )
            self._conn.commit()
            inserted = cur.rowcount == 1
            if inserted:
                log.info("DB insert_run: run_id=%s pr=%d status=%s cause=%s", job.run_id, job.pr, job.status, job.cause)
            return inserted
        except sqlite3.OperationalError:
            self._retry(lambda: self.insert_run(job))
            return False

    def claim_run(self, run_id: str) -> bool:
        """Set running in a tx; only one worker may claim (REQ-NF-005)."""
        now = int(time.time())
        cur = self._conn.execute(
            "UPDATE review_runs SET status='running', updated_at=? "
            "WHERE run_id=? AND status='queued'",
            (now, run_id),
        )
        self._conn.commit()
        claimed = cur.rowcount == 1
        if claimed:
            log.info("DB claim_run: run_id=%s status=running", run_id)
        return claimed

    def acquire_lease(self, run_id: str, lease_ttl_seconds: int = _LEASE_TTL) -> bool:
        """UTS-004-A3: re-acquire a lease whose timestamp is older than the TTL."""
        cutoff = int(time.time()) - lease_ttl_seconds
        cur = self._conn.execute(
            "UPDATE review_runs SET status='running', updated_at=? "
            "WHERE run_id=? AND status='queued' AND updated_at < ?",
            (int(time.time()), run_id, cutoff),
        )
        self._conn.commit()
        acquired = cur.rowcount == 1
        if acquired:
            log.info("DB acquire_lease: run_id=%s status=running", run_id)
        return acquired

    def set_status(self, run_id: str, status: str) -> None:
        assert status in _RUN_STATES, f"invalid run status {status!r}"
        self._conn.execute(
            "UPDATE review_runs SET status=?, updated_at=? WHERE run_id=?",
            (status, int(time.time()), run_id),
        )
        self._conn.commit()
        log.info("DB set_status: run_id=%s status=%s", run_id, status)

    def update_head(self, run_id: str, head: str) -> None:
        self._conn.execute(
            "UPDATE review_runs SET head=?, updated_at=? WHERE run_id=?",
            (head, int(time.time()), run_id),
        )
        self._conn.commit()
        log.info("DB update_head: run_id=%s head=%s", run_id, head)

    def get_run(self, run_id: str) -> ReviewJob:
        row = self._conn.execute(
            "SELECT run_id, owner, repo, pr, head, model, status, attempts, cause "
            "FROM review_runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return ReviewJob(
            run_id=row[0], owner=row[1], repo=row[2], pr=row[3], head=row[4],
            model=row[5], status=row[6], attempts=row[7], cause=row[8],
        )

    def has_run_for_head(self, owner: str, repo: str, pr: int, head: str) -> bool:
        """Check if a review run has already been recorded for a specific owner/repo/pr/head."""
        row = self._conn.execute(
            "SELECT 1 FROM review_runs WHERE owner=? AND repo=? AND pr=? AND head=?",
            (owner, repo, pr, head),
        ).fetchone()
        return row is not None

    def recover_orphans(self, lease_ttl_seconds: int = 3600) -> int:
        """Boot sweep: requeue `running` runs older than the lease TTL (ARCH-011)."""
        now = int(time.time())
        cutoff = now - lease_ttl_seconds
        cur = self._conn.execute(
            "UPDATE review_runs SET status='queued', updated_at=? "
            "WHERE status='running' AND updated_at <= ?",
            (now, cutoff),
        )
        self._conn.commit()
        return cur.rowcount

    def reconcile_open_jobs(self) -> list[ReviewJob]:
        """Resume queued/pending runs after a crash (ARCH-011)."""
        rows = self._conn.execute(
            "SELECT run_id, owner, repo, pr, head, model, status, attempts, cause "
            "FROM review_runs WHERE status IN ('pending_ci', 'queued')"
        ).fetchall()
        return [
            ReviewJob(run_id=r[0], owner=r[1], repo=r[2], pr=r[3], head=r[4],
                      model=r[5], status=r[6], attempts=r[7], cause=r[8])
            for r in rows
        ]

    # --- repos (cache metadata) ---

    def get_repo(self, key: str) -> Optional[CachedRepo]:
        row = self._conn.execute(
            "SELECT owner, repo, path, last_used FROM repos WHERE key=?", (key,)
        ).fetchone()
        if row is None:
            return None
        return CachedRepo(owner=row[0], repo=row[1], path=row[2], last_used=row[3])

    def put_repo(self, entry: CachedRepo) -> None:
        self._conn.execute(
            "INSERT INTO repos (key, owner, repo, path, last_used) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET path=excluded.path, last_used=excluded.last_used",
            (f"{entry.owner}/{entry.repo}", entry.owner, entry.repo, entry.path, entry.last_used),
        )
        self._conn.commit()

    def touch_repo(self, key: str, ts: int) -> None:
        self._conn.execute("UPDATE repos SET last_used=? WHERE key=?", (ts, key))
        self._conn.commit()

    def list_repos(self) -> list[CachedRepo]:
        return [
            CachedRepo(owner=r[0], repo=r[1], path=r[2], last_used=r[3])
            for r in self._conn.execute(
                "SELECT owner, repo, path, last_used FROM repos ORDER BY last_used ASC"
            ).fetchall()
        ]

    def remove_repo(self, key: str) -> None:
        self._conn.execute("DELETE FROM repos WHERE key=?", (key,))
        self._conn.commit()

    def _retry(self, fn) -> None:
        for attempt in range(self._max_retries):
            try:
                fn()
                return
            except sqlite3.OperationalError:
                time.sleep(0.5 * (attempt + 1))
        raise RuntimeError("state DB locked; retries exhausted")

    def close(self) -> None:
        self._conn.close()
