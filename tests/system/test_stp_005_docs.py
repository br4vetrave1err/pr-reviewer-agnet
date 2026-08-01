# Implements: STP-005-A, STP-005-B, SYS-005, REQ-006, REQ-IF-006
"""STP-005-A/B: docs load contract and graceful degradation."""

import logging

import pytest

from docs.loader import DocsLoader


def test_sts_005_a1_docs_loaded_not_degraded(tmp_path):
    root = tmp_path / "specs" / "acme" / "app"
    root.mkdir(parents=True)
    (root / "README.md").write_text("# canonical docs", encoding="utf-8")
    docs = DocsLoader(str(tmp_path / "specs")).load("acme", "app")
    assert docs.degraded is False
    assert "README.md" in docs.files
    assert "canonical docs" in docs.content["README.md"]


def test_sts_005_a2_missing_folder_degraded(tmp_path):
    docs = DocsLoader(str(tmp_path / "specs")).load("acme", "nope")
    assert docs.degraded is True
    assert docs.files == [] and docs.content == {}


def test_sts_005_b1_unreadable_tree_warns_and_proceeds(tmp_path, caplog, monkeypatch):
    from pathlib import Path

    root = tmp_path / "specs" / "acme" / "app"
    root.mkdir(parents=True)
    (root / "README.md").write_text("x", encoding="utf-8")
    loader = DocsLoader(str(tmp_path / "specs"))

    def boom(self, pattern):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "glob", boom)
    with caplog.at_level(logging.WARNING):
        docs = loader.load("acme", "app")
    monkeypatch.undo()
    assert docs.degraded is True  # run proceeds with no docs
    assert docs.content == {}
    assert any("permission denied" in r.message for r in caplog.records)
