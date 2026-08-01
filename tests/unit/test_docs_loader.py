# Implements: UTP-007-A, UTS-007-A1, UTS-007-A2, MOD-007, ARCH-005, REQ-006
"""Unit tests — MOD-007 (Docs Loader)."""

from docs.loader import DocsLoader


def test_uts_007_a1_docs_folder_found(tmp_path):
    folder = tmp_path / "specs" / "acme" / "app"
    folder.mkdir(parents=True)
    (folder / "architecture.md").write_text("# Arch", encoding="utf-8")
    loader = DocsLoader(tmp_path / "specs")
    docs = loader.load("acme", "app")
    assert docs.degraded is False
    assert docs.files == ["architecture.md"]
    assert docs.content["architecture.md"] == "# Arch"


def test_uts_007_a2_missing_folder_degrades(tmp_path):
    loader = DocsLoader(tmp_path / "specs")
    docs = loader.load("acme", "missing")
    assert docs.degraded is True
    assert docs.files == []
