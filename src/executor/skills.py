# Implements: MOD-019, ARCH-006, SYS-006, REQ-017, REQ-007, REQ-CN-003, REQ-IF-003
"""Skill Set Selector (MOD-019 / ARCH-006).

REQ-017: the defined agent skill set is the base for review. The base
``/code-review`` skill is always present; situational skills
(``/diagnosing-bugs``, ``/resolving-merge-conflicts``) are appended based on
findings. Repo skills (``AGENTS.md``/``.opencode/``) and vendored
``.agents/skills/`` are unioned in (REQ-007 / REQ-CN-003). Deduplicated,
bounded.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("pr_reviewer.executor.skills")


class SkillSetSelector:
    def __init__(self, base_skill: str = "/code-review", situational: Optional[list[str]] = None):
        self._base = base_skill
        self._situational = situational or ["/diagnosing-bugs", "/resolving-merge-conflicts"]

    def select(self, findings, repo_skills: Optional[list[str]] = None, vendored_skills: Optional[list[str]] = None) -> list[str]:
        skills = [self._base]  # always present (REQ-017)

        for s in self._situational:
            if any(getattr(f, "type", None) == _situational_type(s) for f in findings):
                skills.append(s)

        for extra in (vendored_skills or []) + (repo_skills or []):
            if extra not in skills:
                skills.append(extra)

        return skills[: 16]  # bounded

    def missing_from_disk(self, skills: list[str], roots: list[str | Path]) -> list[str]:
        """ARCH-006: warn for skills absent on disk; base skill still used."""
        missing = []
        for s in skills:
            if not any(_skill_exists(root, s) for root in roots):
                missing.append(s)
        return missing


def _skill_exists(root: str | Path, skill: str) -> bool:
    name = skill.strip("/")
    return (Path(root) / name / "SKILL.md").exists() or (Path(root) / name).exists()


def _situational_type(skill: str) -> str:
    mapping = {"/diagnosing-bugs": "bug", "/resolving-merge-conflicts": "merge_conflict"}
    return mapping.get(skill, "review")
