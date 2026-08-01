# Implements: UTP-018-A, UTS-018-A1, UTS-018-A2, MOD-018, ARCH-013, REQ-NF-003, REQ-NF-004
"""Unit tests — MOD-018 (Rate Limiter)."""

import observability.ratelimit as rl


def test_uts_018_a1_attempt_one_delay_within_bounds():
    for _ in range(50):
        d = rl.schedule_retry(1, "github")
        assert 7.5 <= d <= 12.5  # 10s base, +-25% jitter


def test_uts_018_a2_delay_saturates_at_max():
    for attempt in range(10, 40):
        d = rl.backoff_delay(attempt, "github")
        assert d <= rl._BACKOFF_TABLE["github"]["max_ms"] / 1000.0 + 0.5


def test_uts_018_a2_deterministic_backoff_no_jitter():
    assert rl.backoff_delay(1, "github") == 10.0
    assert rl.backoff_delay(2, "github") == 20.0
