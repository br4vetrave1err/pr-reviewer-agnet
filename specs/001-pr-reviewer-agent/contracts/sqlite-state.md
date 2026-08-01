# Contract: SQLite State Schema (ARCH-011 State Store)

<!-- v-model:traces
  architecture: [ARCH-011]
  modules:      [MOD-015]
  version:      v0.8.0
-->

Source: `v-model/architecture-design.md` §Interface View — ARCH-011. Backed by REQ-IF-005, REQ-NF-005. Full data view in `data-model.md`.

## Tables

| Table | Purpose | Unique constraint |
|-------|---------|-------------------|
| `review_runs` | One review attempt (stores status, CI gate state, CI failure diagnostics, scope findings, validator filter results, model fallback metadata, security scan results) | `(owner, repo, pr_number, head_sha, model_alias)` |
| `repos` | Repo managed/deny status + defaults | PK `(owner, name)` |
| `model_aliases` | Alias → provider/model/auth_ref | PK `(alias)` |
| `repo_config` | Per-repo overrides (source of truth for managed repos) | PK `(owner, repo)` |

## Run State Machine

```
pending_ci ──▶ queued ──▶ running ──▶ posted
    │            │            ├──▶ ci-failed   (CI gate failed → diagnosis comment)
    │            │            └──▶ partial     (incomplete report comment)
    │            └──▶ skipped (dedup/closed/not-self/denied/CI-timeout)
    └──▶ skipped (CI timeout: "CI hasn't completed" comment)
```

- `pending_ci`: accepted, waiting on gating CI runs for that head to complete (or the no-CI bypass window, or the wait cap).
- `queued`: CI green (or bypassed), waiting for the single worker slot.
- `running` → `posted` / `ci-failed` / `partial` / `skipped` (terminal).
- Concurrency is **1** — one review at a time; different model aliases at the same head are distinct runs and queue serially.

## Key Operations

| Operation | Semantics |
|-----------|-----------|
| `dedupInsert(owner, repo, pr, head, model)` | `INSERT OR IGNORE`; unique-index violation is coalesced as a duplicate, not a failure (ARCH-011) |
| `updateRun(runId, patch)` | Transactional state machine transitions per the diagram above |
| `markPostedByMarker(owner, repo, pr, head, model)` | Idempotency anchor: reconcile/dedup treats a run as `posted` if a GitHub-side comment carries the `_Reviewed by PR Review Agent · run <run_id>_` marker — DB state is advisory, the marker is authoritative (REQ-NF-005) |
| Recovery | On restart, orphaned `running`/`pending_ci` jobs are requeued; no double-post (REQ-NF-005, SCN-NF-001-A1) |

## Concurrency

WAL mode for cross-worker consistency (ARCH-003). Dedup insert and status transitions are single transactions.

## Verification

ATP-IF-005-A (SCN-IF-005-A1), ATP-NF-005-A (SCN-NF-005-A1), ATP-NF-001-A (SCN-NF-001-A1).
