# Implements: MOD-003, ARCH-002, SYS-011, REQ-013
"""Comment Command Parser (MOD-003 / SYS-011).

Parses PR comment commands ``@review --model <alias>``. A body with no
``@review`` token yields ``None``. A malformed ``@review`` command (unknown
flag) raises :class:`CommandSyntaxError`, which the caller turns into a help
reply listing valid aliases (REQ-013, ARCH-002 `malformed-command`).
"""

from __future__ import annotations

import re

from domain import Command

_HAS_TOKEN_RE = re.compile(r"(@review|\breview\b|<@[\w-]+>)", re.IGNORECASE)
_MODEL_RE = re.compile(r"--model\s+(\S+)", re.IGNORECASE)
_FLAG_RE = re.compile(r"--[\w-]+")


class CommandSyntaxError(Exception):
    """Raised for an ``@review`` command with unknown/malformed syntax."""


def usage(valid_aliases: list[str]) -> str:
    aliases = ", ".join(sorted(valid_aliases))
    return (
        "Usage: `@review [--model <alias>]`\n"
        f"Valid model aliases: {aliases}\n"
        "Unknown or malformed commands are ignored."
    )


def parse_command(body: str) -> Command | None:
    """REQ-013: no token -> None; malformed command -> CommandSyntaxError."""
    body = body or ""
    if not _HAS_TOKEN_RE.search(body):
        return None
    flags = _FLAG_RE.findall(body)
    if any(f != "--model" for f in flags):
        raise CommandSyntaxError(body)
    m = _MODEL_RE.search(body)
    return Command(kind="review", model=m.group(1) if m else None)
