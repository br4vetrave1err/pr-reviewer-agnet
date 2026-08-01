# Implements: ATP-007-A, ATP-017-A, ATP-CN-003-A
"""ATP-007-A / ATP-017-A / ATP-CN-003-A: repo skills + vendored skill set.

User journeys: repo skills/AGENTS.md are available to the agent; the vendored
skill set (/code-review base + situational skills) is assembled and available;
the defined skill set is used as the review base and situational skills are
applied on matching findings.
"""

from tests.acceptance.conftest import high_finding, pull_request_payload
from domain import Finding, Severity


async def test_scn_007_a1_repo_skill_available(journey):
    checkout = journey.clone_cache.root + "/acme/app"
    import os

    os.makedirs(checkout, exist_ok=True)
    with open(os.path.join(checkout, "AGENTS.md"), "w", encoding="utf-8") as fh:
        fh.write("Tests run with pytest.\n")

    await journey.deliver_async(pull_request_payload())
    await journey.run_until(lambda: len(journey.runner.calls) >= 1)
    assert journey.runner.calls[0].repo == "app"


def test_scn_007_a2_vendored_skills_available(config):
    from executor.skills import SkillSetSelector

    selector = SkillSetSelector(config.agent_skill_set.base, config.agent_skill_set.situational)
    skills = selector.select([], vendored_skills=["/code-review", "/diagnosing-bugs", "/resolving-merge-conflicts"])
    assert "/code-review" in skills
    assert "/diagnosing-bugs" in skills
    assert "/resolving-merge-conflicts" in skills


def test_scn_017_a1_base_skill_always_present(config):
    from executor.skills import SkillSetSelector

    selector = SkillSetSelector(config.agent_skill_set.base, config.agent_skill_set.situational)
    skills = selector.select([])  # no bug / conflict findings
    assert skills[0] == "/code-review"
    assert "/diagnosing-bugs" not in skills
    assert "/resolving-merge-conflicts" not in skills


def test_scn_017_a2_bug_finding_applies_diagnosing_bugs(config):
    from executor.skills import SkillSetSelector

    selector = SkillSetSelector(config.agent_skill_set.base, config.agent_skill_set.situational)
    skills = selector.select([Finding(path="a", severity=Severity.HIGH, type="bug")])
    assert "/code-review" in skills
    assert "/diagnosing-bugs" in skills


def test_scn_017_a3_conflict_finding_applies_merge_skill(config):
    from executor.skills import SkillSetSelector

    selector = SkillSetSelector(config.agent_skill_set.base, config.agent_skill_set.situational)
    skills = selector.select([Finding(path="b", severity=Severity.MEDIUM, type="merge_conflict")])
    assert "/resolving-merge-conflicts" in skills


def test_scn_017_a4_defined_set_available_alongside_repo(config):
    from executor.skills import SkillSetSelector

    selector = SkillSetSelector(config.agent_skill_set.base, config.agent_skill_set.situational)
    skills = selector.select(
        [Finding(path="x", severity=Severity.HIGH, type="bug")],
        repo_skills=["/repo-custom"],
        vendored_skills=["/code-review", "/diagnosing-bugs", "/resolving-merge-conflicts"],
    )
    assert skills[:3] == ["/code-review", "/diagnosing-bugs", "/resolving-merge-conflicts"]
    assert "/repo-custom" in skills


def test_scn_cn_003_a1_three_skills_vendored_in_repo():
    from pathlib import Path

    skills_root = Path(__file__).resolve().parents[2] / ".agents" / "skills"
    for skill in ("code-review", "diagnosing-bugs", "resolving-merge-conflicts"):
        assert (skills_root / skill / "SKILL.md").is_file(), skill  # REQ-CN-003
