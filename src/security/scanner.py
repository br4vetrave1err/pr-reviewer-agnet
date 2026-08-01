# Implements: MOD-011, ARCH-008, SYS-008, REQ-009
"""Security Scan Runner (MOD-011 / SYS-008).

Runs gitleaks against the full checkout (REQ-009) and normalizes findings.
LLM security review of the diff happens in-session inside the single review
run (MOD-012). Missing tool -> phase skipped + logged (ARCH-008
`tool-missing`); scan timeout -> phase marked partial. Never aborts.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Optional

from domain import Finding, Severity

log = logging.getLogger("pr_reviewer.security.scanner")


@dataclass
class SecReport:
    secrets: list[Finding] = field(default_factory=list)
    partial: bool = False
    skipped: bool = False


class SecurityScanRunner:
    def __init__(self, gitleaks_bin: str = "gitleaks", timeout_seconds: int = 300):
        self._bin = gitleaks_bin
        self._timeout = timeout_seconds

    def should_scan(self, ci_status: Optional[str]) -> bool:
        """UTS-011-A2: no scans on red heads (green/absent CI only)."""
        return ci_status in (None, "success", "green")

    def scan(self, checkout: str) -> SecReport:
        try:
            proc = subprocess.run(
                [self._bin, "detect", "--source", checkout, "--report-format", "json", "--no-banner"],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except FileNotFoundError:
            log.warning("gitleaks not found; secrets phase skipped (ARCH-008 tool-missing)")
            return SecReport(skipped=True)
        except subprocess.TimeoutExpired:
            log.error("gitleaks timed out; secrets phase marked partial")
            return SecReport(partial=True)

        if proc.returncode not in (0, 1):  # 1 = findings present
            log.warning("gitleaks exited %d; treating as partial", proc.returncode)
            return SecReport(partial=True)

        findings: list[Finding] = []
        if proc.stdout.strip():
            try:
                raw = json.loads(proc.stdout)
            except json.JSONDecodeError:
                raw = []
            for item in raw if isinstance(raw, list) else []:
                findings.append(
                    Finding(
                        path=str(item.get("File", "")),
                        line=item.get("StartLine"),
                        severity=Severity.HIGH,
                        title="Potential secret detected",
                        detail=str(item.get("Description", ""))[:300],
                        type="secrets",
                    )
                )
        return SecReport(secrets=findings)
