# Implements: ATP-IF-003-A
"""ATP-IF-003-A: headless opencode CLI subprocess contract.

User journey: given a checkout, docs, and a resolved model, spawning
`opencode run` returns a parseable JSON result or a classified non-zero exit.
"""

import json
import subprocess

import pytest
from executor.skills import SkillSetSelector
from models.registry import ModelRegistry
from runner.workspace import PromptContext, WorkspaceRunner
from tests.acceptance.conftest import config


class _FakeProc:
    def __init__(self, rc=0, out=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = ""


@pytest.mark.asyncio
async def test_scn_if_003_a1_headless_opencode_run(tmp_path, monkeypatch, config):
    argv = []

    def fake_run(cmd, **kw):
        argv.append(cmd)
        return _FakeProc(out='{"summary": "ok", "findings": []}')

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = WorkspaceRunner(ModelRegistry(config), SkillSetSelector())
    result = await runner.run(
        str(tmp_path),
        PromptContext(head="h", owner="acme", repo="app", pr=1, docs_text="",
                      diff="", model_alias="free", auth_ref="X", skill_args=["/code-review"]),
    )

    assert argv[0][0] == "opencode" and argv[0][1] == "run"  # one-off CLI
    assert "--non-interactive" in argv[0]
    assert result.exit_code == 0
    assert result.summary == "ok"


@pytest.mark.asyncio
async def test_scn_if_003_a1_nonzero_exit_classified(tmp_path, monkeypatch, config):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeProc(rc=1))
    runner = WorkspaceRunner(ModelRegistry(config), SkillSetSelector())
    result = await runner.run(
        str(tmp_path),
        PromptContext(head="h", owner="acme", repo="app", pr=1, docs_text="",
                      diff="", model_alias="free", auth_ref="X", skill_args=[]),
    )
    assert result.exit_code == 1
    assert result.retryable is True  # exit 1 is transient/provider (REQ-014)


@pytest.mark.asyncio
async def test_scn_if_003_a1_unparseable_output_no_crash(tmp_path, monkeypatch, config):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeProc(rc=0, out="not json"))
    runner = WorkspaceRunner(ModelRegistry(config), SkillSetSelector())
    result = await runner.run(
        str(tmp_path),
        PromptContext(head="h", owner="acme", repo="app", pr=1, docs_text="",
                      diff="", model_alias="free", auth_ref="X", skill_args=[]),
    )
    assert result.exit_code == 0  # schema violation handled, no crash (REQ-IF-003)
