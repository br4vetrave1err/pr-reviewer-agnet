# Implements: UTP-019-A, UTS-019-A1, UTS-019-A2, UTS-019-A3, UTS-019-A4, MOD-019, ARCH-006, REQ-017, REQ-007, REQ-CN-003
"""Unit tests — MOD-019 (Skill Set Selector)."""

from domain import Finding
from executor.skills import SkillSetSelector


def _finding(finding_type):
    return Finding(path="x", type=finding_type)


def test_uts_019_a1_base_skill_always_present():
    selector = SkillSetSelector()
    skills = selector.select([])
    assert "/code-review" in skills


def test_uts_019_a2_bug_finding_adds_diagnosing_bugs():
    selector = SkillSetSelector()
    skills = selector.select([_finding("bug")])
    assert "/diagnosing-bugs" in skills


def test_uts_019_a3_merge_conflict_adds_resolving_skill():
    selector = SkillSetSelector()
    skills = selector.select([_finding("merge_conflict")])
    assert "/resolving-merge-conflicts" in skills


def test_uts_019_a4_repo_and_vendored_merged_deduped():
    selector = SkillSetSelector()
    skills = selector.select(
        [_finding("bug")],
        repo_skills=["/code-review", "/team-custom"],
        vendored_skills=["/diagnosing-bugs"],
    )
    assert skills.count("/code-review") == 1
    assert skills.count("/diagnosing-bugs") == 1
    assert "/team-custom" in skills


def test_skill_missing_from_disk_flagged():
    selector = SkillSetSelector()
    missing = selector.missing_from_disk(["/does-not-exist"], [])
    assert "/does-not-exist" in missing
