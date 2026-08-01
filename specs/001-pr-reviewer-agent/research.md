# Research: GitHub PR Review Agent

<!-- v-model:traces
  requirements: [REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-006, REQ-007, REQ-008, REQ-009, REQ-010, REQ-011, REQ-012, REQ-013, REQ-014, REQ-015, REQ-016, REQ-017, REQ-NF-001, REQ-NF-002, REQ-NF-003, REQ-NF-004, REQ-NF-005, REQ-NF-006, REQ-NF-007, REQ-IF-001, REQ-IF-002, REQ-IF-003, REQ-IF-004, REQ-IF-005, REQ-IF-006, REQ-CN-001, REQ-CN-002, REQ-CN-003, REQ-CN-004]
  system:       [SYS-001, SYS-002, SYS-003, SYS-004, SYS-005, SYS-006, SYS-007, SYS-008, SYS-009, SYS-010, SYS-011, SYS-012, SYS-013, SYS-014]
  architecture: [ARCH-001, ARCH-002, ARCH-003, ARCH-004, ARCH-005, ARCH-006, ARCH-007, ARCH-008, ARCH-009, ARCH-010, ARCH-011, ARCH-012, ARCH-013]
  modules:      [MOD-001, MOD-002, MOD-003, MOD-004, MOD-005, MOD-006, MOD-007, MOD-008, MOD-009, MOD-010, MOD-011, MOD-012, MOD-013, MOD-014, MOD-015, MOD-016, MOD-017, MOD-018, MOD-019]
  version:      v0.7.0
-->

## Phase 0 — Research Findings

This document records the Phase 0 research performed before design, per the `/speckit.plan` workflow. It captures the technical decisions validated against the V-Model artifact set (requirements.md, system-design.md, architecture-design.md, module-design.md) and records every `[DERIVED REQUIREMENT]` / `[DERIVED MODULE]` flag found in those artifacts.

## Derived Requirements & Modules

**None.** Grep of `system-design.md`, `architecture-design.md`, and `module-design.md` for `[DERIVED REQUIREMENT]` and `[DERIVED MODULE]` flags returns no matches. The architecture design's "Derived Modules" section confirms: *"None — all modules trace to existing system components."* Every requirement (REQ-001..017, REQ-NF-001..007, REQ-IF-001..006, REQ-CN-001..004) traces through SYS → ARCH → MOD with full coverage per `traceability-matrix.md`. No new identifiers were introduced during research.

## Key Technical Decisions

| # | Decision | Rationale | Source |
|---|----------|-----------|--------|
| 1 | **Docker + GitHub App webhooks** as the trigger channel (not polling) | The user asked for a continuously-running Docker service triggered on PR events; webhooks give immediate, signed delivery. | REQ-CN-001, REQ-001, REQ-IF-002 |
| 2 | **Python 3.11 / FastAPI** implementation | FastAPI gives async webhook handling with pydantic payload validation and an ASGI server (uvicorn); the subprocess-heavy pipeline (opencode, scanners, repo test suites) is language-agnostic so Python carries no penalty. The module design targets a single Python package; the architecture confirms the stack. | MOD overview, ARCH-001 |
| 3 | **SQLite (WAL) + in-process queue** for state and dedup | Crash-safe at-least-once idempotent processing with a documented schema and no external services; SQLite with WAL gives cross-worker consistency. | REQ-IF-005, REQ-NF-005, ARCH-003, ARCH-011 |
| 4 | **Webhook ACK path decoupled from worker pipeline** | REQ-NF-002 demands sub-2s ACK while reviews take minutes; a separate queue/scheduler isolates the paths. | REQ-NF-002, ARCH-001 vs ARCH-003 |
| 5 | **Persistent clone cache with LRU eviction** | Reviews need a full checkout; incremental fetch avoids re-cloning; disk cap prevents unbounded growth. | REQ-005, ARCH-004 |
| 6 | **opencode as an external headless subprocess** | The user's skill system (repo `AGENTS.md` + `.opencode/` + vendored `.agents/skills/`) and model selection are the core value; invoking `opencode run` as a one-off CLI subprocess in the clone with injected context is the execution boundary (no HTTP daemon). | REQ-007, REQ-IF-003, ARCH-006 |
| 7 | **Security pipeline** (gitleaks + in-session LLM review) | REQ-009 requires a full-checkout secrets scan (gitleaks) and an LLM security review of changed files inside the single `/code-review` session; trivy/semgrep are out of scope for v1. | REQ-009, ARCH-008 |
| 8 | **CI gate (Rule B) — suites never run locally** | The agent reviews green heads only: gating `check_run`/`workflow_run` runs on the head must all pass, otherwise a root-cause diagnosis comment is posted (logs fetched via GitHub API). The container never executes the repo's test suites; PR scope + test-compliance are validated (discovery only). | REQ-008, REQ-010, ARCH-007 |
| 9 | **Model aliases + per-PR `@review --model <alias>` comment** | Pluggable providers (opencode free, opencode GO, Google One AI Pro) with a default; unknown aliases reply with valid options. | REQ-013, ARCH-002, ARCH-010 |
| 10 | **This repo's `specs/<owner>/<repo>/` tree as review context**, with graceful degradation | Docs are the review context; absence or unreadability degrades to a no-docs run, never aborts. | REQ-006, REQ-IF-006, ARCH-005 |
| 11 | **Always-COMMENT verdicts (advisory prose)** | Reviews are posted with event `COMMENT`; the verdict (approve / comment / request-changes) is prose in the summary body. Formal `APPROVE`/`REQUEST_CHANGES` review events are never used — advisory by default, no hard-blocking. | REQ-012 |
| 12 | **Retry with backoff + partial-report comments** | Transient failures retry; non-completable reviews post a short "what ran / what didn't" comment instead of silent failure. | REQ-014, ARCH-003 |
| 13 | **Secrets via gitignored `.env` (`env_file`) only** | PAT, webhook secret, and provider keys never in repo, logs, or review output; the container builds opencode's `auth.json` from `OPENCODE_GO_TOKEN` at boot. | REQ-NF-004 |
| 14 | **Single app-layer model definition, config-only switching** | Each provider alias is defined exactly once (Model Registry, `providers` in `config.yaml`); the active model is `default_model`, switchable at runtime via `switch_default` (credit-exhaustion fallback) without redeploy or rebuild. Per-PR `@review --model` overrides are preserved per run and never mutate the registry. | REQ-016, ARCH-010, SYS-010, MOD-014 |
| 15 | **Defined agent skill set (`/code-review` base + situational)** | The agent ships a declared skill set: `/code-review` runs on every review; `/diagnosing-bugs` and `/resolving-merge-conflicts` attach only for the matching analysis context. A Skill Set Selector (`MOD-019`) chooses the subset per run; unknown skills degrade to the base skill set. | REQ-017, ARCH-006, ARCH-012, MOD-019 |
| 16 | **Market-skills research captured as reference, not a dependency** | Survey of published agent skills found `farmage/opencode-skills` → `skills/code-reviewer` (MIT, v1.1.0): a code-review specialist whose SKILL.md metadata (domain: quality; role: specialist; scope: review; output-format: report; allowed tools Read/Grep/Glob; related skills architecture-designer/code-documenter/security-reviewer/test-master/the-fool) informed REQ-017's base-skill requirements. Market skills are not vendored; the defined skill set (`/code-review`, `/diagnosing-bugs`, `/resolving-merge-conflicts`) is vendored into the repo's `.agents/skills/` in the image. | REQ-017 |

## Market Skills Research — REQ-017 (reference)

Surveyed publicly published agent skills relevant to a defined PR-reviewer skill set.

| Skill | Source | License / Ver | Metadata (domain · role · scope · output-format) | Allowed tools | Related skills | Assessment |
|-------|--------|---------------|--------------------------------------------------|---------------|----------------|------------|
| `code-reviewer` | `farmage/opencode-skills` `skills/code-reviewer/SKILL.md` | MIT · v1.1.0 | quality · specialist · review · report | Read, Grep, Glob | architecture-designer, code-documenter, security-reviewer, test-master, the-fool | Strong domain fit for the base skill; read-only review posture aligns with REQ-CN-004. Informational — not vendored. |

## Open Questions

None blocking. Two items are tracked as early tasks rather than open questions:

- **Constitution ratification**: `.specify/memory/constitution.md` is still the stock template; ratifying real principles is an early task (noted in `plan.md` Constitution Check).
- **opencode headless output contract**: the exact machine-readable output shape of a headless opencode run will be pinned during implementation of `MOD-006` (Workspace Runner) against the installed opencode version (REQ-IF-003).
