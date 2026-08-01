# Implements: MOD-018, ARCH-013, SYS-014, REQ-NF-003
"""Rate Limiter (MOD-018 / ARCH-013).

Exponential backoff with jitter for GitHub 403/429 and provider outages
(REQ-NF-003). Base delays per category; caps at max backoff.
"""

from __future__ import annotations

import random

_BACKOFF_TABLE = {
    "github": {"base_ms": 10_000, "max_ms": 300_000},
    "provider": {"base_ms": 5_000, "max_ms": 120_000},
}
_JITTER = 0.25  # +-25%


def schedule_retry(attempt: int, category: str = "github", jitter_ratio: float = _JITTER) -> float:
    """Return the retry delay in seconds for the given attempt (1-based)."""
    spec = _BACKOFF_TABLE.get(category, _BACKOFF_TABLE["github"])
    delay = spec["base_ms"] * (2 ** (attempt - 1))
    delay = min(delay, spec["max_ms"])
    delay = delay * (1 - jitter_ratio + random.random() * 2 * jitter_ratio)
    return delay / 1000.0


def backoff_delay(attempt: int, category: str = "github", jitter_ratio: float = 0.0) -> float:
    """Deterministic backoff (no jitter) for boundary tests (UTP-018-A)."""
    spec = _BACKOFF_TABLE.get(category, _BACKOFF_TABLE["github"])
    delay = spec["base_ms"] * (2 ** (attempt - 1))
    delay = min(delay, spec["max_ms"])
    if jitter_ratio > 0:
        delay = delay * (1 - jitter_ratio + random.random() * 2 * jitter_ratio)
    return delay / 1000.0
