# Implements: UTP-003-A, UTS-003-A1, UTS-003-A2, UTS-003-A3, MOD-003, ARCH-002, REQ-013
"""Unit tests — MOD-003 (Command Parser)."""

import pytest

from filter.command import CommandSyntaxError, parse_command, usage


def test_uts_003_a1_valid_command_with_model():
    cmd = parse_command("@review --model gemini")
    assert cmd.kind == "review"
    assert cmd.model == "gemini"


def test_uts_003_a1_valid_command_default_model():
    cmd = parse_command("@review")
    assert cmd.kind == "review"
    assert cmd.model is None


def test_uts_003_a2_no_command_token_returns_none():
    assert parse_command("LGTM, nice work") is None
    assert parse_command("") is None


def test_uts_003_a3_unknown_flag_raises():
    with pytest.raises(CommandSyntaxError):
        parse_command("@review --bogus flag")


def test_usage_lists_aliases():
    text = usage(["gemini", "free"])
    assert "gemini" in text
    assert "free" in text
