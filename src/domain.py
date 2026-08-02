# Implements: MOD-001, MOD-002, MOD-003, MOD-007, MOD-008, MOD-009, MOD-010, MOD-012, MOD-014, MOD-019
"""Shared domain types for the PR Review Agent.

Plain dataclasses shared across the module set. Every module carries its own
`Implements:` directives; this file exists to keep the cross-module data
shapes (event, decision, finding, docs, resolved model) in one place so the
module algorithms stay focused on behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    """Finding severity ordering (high -> low)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


SEVERITY_ORDER = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}


@dataclass
class NormalizedEvent:
    """Typed, signature-validated webhook event (MOD-001 normalization)."""

    event: str
    action: str
    owner: str
    repo: str
    pr_number: Optional[int] = None
    head_sha: Optional[str] = None
    author: Optional[str] = None
    requested_reviewers: list[str] = field(default_factory=list)
    comment_body: Optional[str] = None
    ci_status: Optional[str] = None
    pr_state: Optional[str] = None
    sender: Optional[str] = None
    draft: bool = False


@dataclass
class Decision:
    """Trigger filter output (MOD-002)."""

    action: str  # enqueue | skip | reply | advance-ci
    reason: Optional[str] = None
    owner: Optional[str] = None
    repo: Optional[str] = None
    pr: Optional[int] = None
    head: Optional[str] = None
    model: Optional[str] = None
    target: Optional[object] = None


@dataclass
class Command:
    """Parsed `@review` comment command (MOD-003)."""

    kind: str = "review"
    model: Optional[str] = None


@dataclass
class Finding:
    """A single review finding (normalized across all phases)."""

    path: str
    line: Optional[int] = None
    severity: Severity = Severity.LOW
    title: str = ""
    detail: str = ""
    type: str = "review"  # bug | merge_conflict | security | scope | compliance | secrets


@dataclass
class Docs:
    """Docs loaded from the local specs tree (MOD-007)."""

    files: list[str] = field(default_factory=list)
    content: dict[str, str] = field(default_factory=dict)
    degraded: bool = False


@dataclass
class ResolvedModel:
    """Resolved provider/model/auth reference (MOD-014)."""

    alias: str
    provider: str
    model: str
    auth_ref: str  # env var NAME, never the value (REQ-NF-004)


@dataclass
class ReviewResult:
    """Result of a workspace run (MOD-008) â€” parsed opencode JSON."""

    summary: str = ""
    findings: list[Finding] = field(default_factory=list)
    exit_code: int = 0
    retryable: bool = False


@dataclass
class GateResult:
    """CI gate resolution (MOD-009)."""

    passed: bool
    reason: str = ""
    details: list[str] = field(default_factory=list)
    ci_status: Optional[str] = None
