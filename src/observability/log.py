# Implements: MOD-017, ARCH-013, SYS-014, REQ-015, REQ-NF-001, REQ-NF-007
"""Logger & Run Records (MOD-017 / SYS-014).

Structured JSON log lines to stdout (REQ-015) and per-run persisted records
under ``.runs/<run_id>/run.jsonl``. Log failure is non-blocking â€” log-loss is
tolerated (REQ-NF-001 / ARCH-013).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("pr_reviewer.observability.log")

RUNS_ROOT = Path(".runs")


class RunLogger:
    _REDACT_KEYS = {"token", "secret", "password", "authorization", "auth", "key", "api_key", "apikey"}

    def __init__(self, runs_root: str | Path = RUNS_ROOT, stream=None, secrets: Optional[list[str]] = None):
        self._runs_root = Path(runs_root)
        self._stream = stream  # default: write through to stdlib logging
        self._secrets = [s for s in (secrets or []) if s]

    def log(self, run_id: Optional[str], phase: str, level: str, **fields) -> None:
        redacted = self._redact(fields)
        line = {
            "ts": _now_ms(),
            "runId": run_id,
            "phase": phase,
            "level": level,
            **redacted,
        }
        text = json.dumps(line, ensure_ascii=False)
        if self._stream is not None:
            print(text, file=self._stream)
        else:
            getattr(log, level.lower(), log.info)("run=%s phase=%s %s", run_id, phase, redacted)
        if run_id:
            self._append(run_id, text)

    def _redact(self, fields: dict) -> dict:
        """UTS-017-A2: never emit secret values; mask by key name or value."""
        out: dict = {}
        for k, v in fields.items():
            if isinstance(v, str) and any(s in v for s in self._secrets):
                out[k] = "[REDACTED]"
            elif k.lower() in self._REDACT_KEYS:
                out[k] = "[REDACTED]"
            else:
                out[k] = v
        return out

    def _append(self, run_id: str, text: str) -> None:
        try:
            d = self._runs_root / run_id
            d.mkdir(parents=True, exist_ok=True)
            with (d / "run.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(text + "\n")
        except OSError as exc:
            log.warning("run record write failed (non-blocking): %s", exc)


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)
