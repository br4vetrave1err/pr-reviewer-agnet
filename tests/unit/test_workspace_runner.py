# Implements: UTP-008-A, UTS-008-A1, UTS-008-A2, MOD-008, ARCH-006, REQ-007, REQ-CN-004
"""Unit tests — MOD-008 (Workspace Runner)."""

import pytest

from runner.workspace import WorkspaceRunner


class FakeRegistry:
    def resolve(self, alias):
        from domain import ResolvedModel

        return ResolvedModel(alias=alias, provider="opencode", model="m", auth_ref="OPENCODE_GO_TOKEN")


class FakeSkills:
    def select(self, findings):
        return ["/code-review"]


def _runner():
    return WorkspaceRunner(FakeRegistry(), FakeSkills(), opencode_bin="opencode")


def test_uts_008_a1_write_operations_rejected():
    r = _runner()
    assert r.guard_read_only(["opencode", "run", "prompt"]) is True
    assert r.guard_read_only(["git", "push", "origin"]) is False
    assert r.guard_read_only(["git", "commit", "-m", "x"]) is False


def test_uts_008_a2_result_parsing(tmp_path, monkeypatch):
    import json
    import subprocess

    stdout = json.dumps(
        {
            "summary": "Looks good",
            "findings": [
                {"path": "a.py", "line": 3, "severity": "high", "title": "XSS", "detail": "sink", "type": "security"}
            ],
        }
    )

    def fake_run(argv, **kw):
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = _runner()
    from runner.workspace import PromptContext

    result = r._parse_result(stdout)
    assert result.exit_code == 0
    assert result.summary == "Looks good"
    assert result.findings[0].title == "XSS"
    assert result.findings[0].severity.value == "high"


@pytest.mark.asyncio
async def test_uts_008_a2_run_async_result(tmp_path, monkeypatch):
    import json
    import subprocess

    stdout = json.dumps({"summary": "ok", "findings": []})

    def fake_run(argv, **kw):
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = _runner()
    from runner.workspace import PromptContext

    result = await r.run(
        str(tmp_path),
        PromptContext(head="sha", owner="a", repo="r", pr=1, docs_text="", diff="diff",
                      model_alias="free", auth_ref="OPENCODE_GO_TOKEN", skill_args=[]),
    )
    assert result.exit_code == 0
    assert result.summary == "ok"
