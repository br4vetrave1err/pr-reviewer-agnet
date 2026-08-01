# Contract: Specs Docs Provider Layout (ARCH-005 Docs Provider)

<!-- v-model:traces
  architecture: [ARCH-005]
  modules:      [MOD-007]
  version:      v0.8.0
-->

Source: `v-model/architecture-design.md` §Interface View — ARCH-005. Backed by REQ-006, REQ-IF-006.

## Location

Docs context is read from **this repository's own `specs/` tree** — no separate `.specs` knowledge repo. `specs_docs_dir: specs` in `config.yaml`; docs live in markdown under folders keyed by `<owner>/<repo>/`.

## Layout

```
<repo_root>/specs/
├── 001-pr-reviewer-agent/       # this feature's own spec (used as context when reviewing this repo)
├── <owner>/<repo>/              # docs for a target repo under review
│   ├── architecture.md
│   └── conventions.md
└── ...
```

For target repo `acme/webapp`, docs are read from the `<repo_root>/specs/acme/webapp/` folder. A missing folder degrades to a review-without-docs (recorded), never aborts.

## Behavior

| Direction | Name | Type | Format |
|-----------|------|------|--------|
| Input | load | `(owner, repo)` | Strings |
| Output | docs | `{files, content}` | Object; empty when folder absent |
| Exception | unreachable | Warning | Degrades, never aborts the run (SCN-006-A2) |

## Verification

ATP-006-A (SCN-006-A1, SCN-006-A2), ATP-IF-006-A (SCN-IF-006-A1).
