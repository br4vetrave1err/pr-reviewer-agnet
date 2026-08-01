# Implements: ITP-005-A, ARCH-005, REQ-006, REQ-IF-006
"""ITP-005-A: docs loader wired into the review prompt; degraded runs proceed."""

import logging

import pytest

from docs.loader import DocsLoader

from tests.integration.conftest import state


def _make_specs(tmp_path):
    root = tmp_path / "specs" / "acme" / "app"
    root.mkdir(parents=True)
    (root / "README.md").write_text("# App docs\nThis is the canonical spec.", encoding="utf-8")
    return tmp_path / "specs"


def test_its_005_a1_docs_present_in_prompt_context(tmp_path):
    loader = DocsLoader(_make_specs(tmp_path))
    docs = loader.load("acme", "app")
    assert not docs.degraded
    assert "README.md" in docs.files
    assert "canonical spec" in docs.content["README.md"]

    from runner.workspace import PromptContext, WorkspaceRunner

    ctx = PromptContext(
        head="abc", owner="acme", repo="app", pr=1,
        docs_text="\n\n".join(docs.content.values()), diff="+x", model_alias="free",
        auth_ref="X", skill_args=[],
    )
    prompt = WorkspaceRunner(None, None)._assemble_prompt(ctx)
    assert "App docs" in prompt  # docs wired into the executor prompt


def test_its_005_a2_missing_docs_tree_degrades(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        loader = DocsLoader(str(tmp_path / "absent"))
        docs = loader.load("acme", "app")

    assert docs.degraded is True
    assert docs.files == [] and docs.content == {}
    assert any("degrading" in r.message for r in caplog.records)  # warning recorded
