# Implements: MOD-007, ARCH-005, SYS-005, REQ-006, REQ-IF-006
"""Docs Loader (MOD-007 / SYS-005).

Reads this repo's ``specs/<owner>/<repo>/`` tree and maps ``<owner>/<repo>/``
folders. Degrades gracefully (no-docs run, recorded) when the folder is
absent or unreadable (REQ-006, ARCH-005 `unreachable`).
"""

from __future__ import annotations

import logging
from pathlib import Path

from domain import Docs

log = logging.getLogger("pr_reviewer.docs.loader")


class DocsLoader:
    def __init__(self, specs_docs_dir: str | Path):
        self._tree_root = Path(specs_docs_dir)

    def load(self, owner: str, repo: str) -> Docs:
        folder = self._tree_root / owner / repo
        if not folder.exists() or not folder.is_dir():
            log.warning("docs folder %s absent; degrading to no-docs run", folder)
            return Docs(files=[], content={}, degraded=True)  # REQ-006 / ARCH-005

        try:
            files = sorted(p.name for p in folder.glob("*.md"))
            content = {f: (folder / f).read_text(encoding="utf-8") for f in files}
        except OSError as exc:
            log.warning("docs tree unreadable: %s", exc)
            return Docs(files=[], content={}, degraded=True)
        return Docs(files=files, content=content, degraded=False)
