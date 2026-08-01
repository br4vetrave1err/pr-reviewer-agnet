# Implements: MOD-010, ARCH-007, SYS-007, REQ-008
"""PR Scope & Test Compliance Validator (MOD-010 / SYS-007).

Validates change scope boundaries (changed files match the PR title/body/
issues) and verifies test-case additions follow repo rules in ``AGENTS.md`` /
``.opencode/``. Discovery + compliance only â€” the container never executes
the repo's test suites (REQ-008).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from domain import Finding, Severity

log = logging.getLogger("pr_reviewer.tests.compliance")

_TEST_PATTERNS = [
    re.compile(r"test_|_test\.|\.test\.|tests?/|spec/", re.IGNORECASE),
]
_MODULE_PATTERNS = [re.compile(r"\.(py|js|ts|tsx|go|rs|java|rb|php)$")]


@dataclass
class ComplianceReport:
    added_test_files: list[str] = field(default_factory=list)
    conventions: list[str] = field(default_factory=list)
    missing_coverage: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)


@dataclass
class PrContext:
    diff_files: list[str]
    title: str = ""
    body: str = ""
    issues: list[str] = field(default_factory=list)


class ComplianceValidator:
    def __init__(self, checkout: str | Path):
        self._checkout = Path(checkout)

    def validate(self, pr_context: PrContext, repo_config: Optional[dict] = None) -> ComplianceReport:
        added_tests = [f for f in pr_context.diff_files if self._is_test_file(f)]
        conventions = self._infer_conventions()
        missing = self._changed_modules_without_tests(pr_context.diff_files, added_tests)
        violations = self._find_violations(pr_context.diff_files, conventions)
        return ComplianceReport(
            added_test_files=added_tests,
            conventions=conventions,
            missing_coverage=missing,
            violations=violations,
        )

    def _is_test_file(self, path: str) -> bool:
        return any(p.search(path) for p in _TEST_PATTERNS)

    def validate_scope(self, pr_context: PrContext, repo_config: Optional[dict] = None) -> list[Finding]:
        """UTP-010-A: scope-violation findings; never aborts the run."""
        scope_tokens = _scope_tokens(pr_context.title, pr_context.body, pr_context.issues)
        findings: list[Finding] = []
        if not scope_tokens:
            return findings
        for f in pr_context.diff_files:
            if self._is_test_file(f) or self._is_doc_file(f):
                continue
            if not any(token in f.lower() for token in scope_tokens):
                findings.append(
                    Finding(
                        path=f,
                        severity=Severity.LOW,
                        title="File outside declared PR scope",
                        detail=f"No match against PR title/body/issues keywords: {', '.join(sorted(scope_tokens))}",
                        type="scope",
                    )
                )
        return findings

    def validate_compliance(self, added_tests: list[str], conventions: list[str]) -> list[Finding]:
        """UTP-010-A: test additions violating repo rules (AGENTS.md / .opencode/)."""
        findings: list[Finding] = []
        for f in added_tests:
            if conventions and not any(part in Path(f).name for part in ("test", "spec", "Test")):
                findings.append(
                    Finding(
                        path=f,
                        severity=Severity.LOW,
                        title="Test file name violates repo conventions",
                        type="compliance",
                    )
                )
        return findings

    @staticmethod
    def _is_doc_file(path: str) -> bool:
        return path.lower().endswith((".md", ".rst", ".txt"))

    def _infer_conventions(self) -> list[str]:
        conventions: list[str] = []
        for name in ("AGENTS.md", "CONTRIBUTING.md", "README.md"):
            f = self._checkout / name
            if f.exists():
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for line in text.splitlines():
                    if re.search(r"test|pytest|jest|spec", line, re.IGNORECASE):
                        conventions.append(f"{name}: {line.strip()[:120]}")
        return conventions[:10]

    def _changed_modules_without_tests(self, diff_files: list[str], added_tests: list[str]) -> list[str]:
        missing: list[str] = []
        for f in diff_files:
            if self._is_test_file(f) or not self._is_module_file(f):
                continue
            module = f.split("/")[-1].rsplit(".", 1)[0]
            if not any(module in t for t in added_tests):
                missing.append(f)
        return missing

    @staticmethod
    def _is_module_file(path: str) -> bool:
        return any(p.search(path) for p in _MODULE_PATTERNS)

    def _find_violations(self, diff_files: list[str], conventions: list[str]) -> list[str]:
        violations: list[str] = []
        for f in diff_files:
            if self._is_test_file(f) and conventions:
                name = Path(f).name
                if not any(part in name for part in ("test", "spec", "Test")):
                    violations.append(
                        f"{f}: test file name does not match inferred conventions"
                    )
        return violations

    def to_findings(self, report: ComplianceReport) -> list[Finding]:
        findings: list[Finding] = []
        for m in report.missing_coverage:
            findings.append(
                Finding(
                    path=m,
                    severity=Severity.MEDIUM,
                    title="Changed module lacks a test addition",
                    detail="A module changed in this PR has no corresponding test case added.",
                    type="compliance",
                )
            )
        for v in report.violations:
            findings.append(
                Finding(path=v, severity=Severity.LOW, title="Test compliance violation", type="compliance")
            )
        return findings


def _scope_tokens(title: str, body: str, issues: list[str]) -> set[str]:
    text = " ".join([title, body, *issues])
    words = set(re.findall(r"[a-z][a-z0-9_\-]{2,}", text.lower()))
    return {w for w in words if not _is_stopword(w)}


def _is_stopword(w: str) -> bool:
    return w in {
        "the", "and", "for", "with", "this", "that", "from", "add", "adds",
        "adding", "fix", "fixes", "fixed", "update", "updates", "updated",
        "support", "supports", "of", "in", "on", "to", "a", "an", "is", "are",
        "was", "were", "be", "by", "it", "its", "if", "not", "as", "at", "or",
    }
