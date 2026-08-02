# Implements: MOD-017, ARCH-013, SYS-014, REQ-015
"""Unit tests for HumanReadableFormatter."""

import logging
from observability.configurator import HumanReadableFormatter


def test_human_readable_formatter():
    record = logging.LogRecord(
        name="pr_reviewer.test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="job_started",
        args=(),
        exc_info=None,
    )
    record.run_id = "12345"
    record.secret_token = "super-secret"

    fmt = HumanReadableFormatter()
    output = fmt.format(record)

    assert "[INFO ]" in output
    assert "[.pr_reviewer.test]" in output or "[pr_reviewer.test]" in output
    assert "job_started" in output
    assert "run_id=12345" in output
    assert "secret_token=[REDACTED]" in output
    assert "super-secret" not in output
