# Data Model: GitHub PR Review Agent

<!-- v-model:traces
  requirements: [REQ-004, REQ-005, REQ-015, REQ-IF-005, REQ-NF-005]
  system:       [SYS-003, SYS-004, SYS-012, SYS-014]
  architecture: [ARCH-003, ARCH-004, ARCH-011, ARCH-013]
  modules:      [MOD-003, MOD-004, MOD-012, MOD-014]
  version:      v0.7.0
-->

## Overview

This is the Data Design view derived from `v-model/system-design.md` (SYS-012 State Store, SYS-004 Repo Clone Cache, SYS-014 Runtime & Observability) and the Key Entities in `spec.md`. Persistent state lives in a SQLite database with the documented schema (REQ-IF-005); run artifacts live on disk under `.runs/`; per-repo docs live in this repo's `specs/<owner>/<repo>/` tree.

## Entities

### Repository

| Field | Type | Notes |
|-------|------|-------|
| owner | TEXT | Repo owner (from `owner/repo`) |
| name | TEXT | Repo name |
| repo_status | ENUM | managed / denied (denylist-only; webhook registration is the allow) |
| clone_path | TEXT | Path in the clone cache (derived from CachedRepo) |
| verdict_policy | ENUM | comment (always COMMENT — from RepoConfig) |

**Sources**: spec.md Key Entities; REQ-003, REQ-005, REQ-012.

### PullRequest

| Field | Type | Notes |
|-------|------|-------|
| owner | TEXT | Repo owner |
| repo | TEXT | Repo name |
| number | INT | PR number |
| head_sha | TEXT | Head commit SHA |
| base_branch | TEXT | Base branch |
| author | TEXT | PR author login |
| requested_reviewers | TEXT[] | Reviewer logins |
| state | ENUM | open / closed / merged |

**Sources**: spec.md Key Entities; REQ-002, REQ-004. Represented in the `review_runs` dedup key (owner, repo, PR, head).

### ReviewRun (→ SQLite `review_runs`)

| Field | Type | Notes |
|-------|------|-------|
| id | INT PK | Auto-increment |
| owner | TEXT | Repo owner |
| repo | TEXT | Repo name |
| pr_number | INT | PR number |
| head_sha | TEXT | Head SHA (part of dedup key) |
| model_alias | TEXT | Resolved model alias (part of dedup key) |
| trigger | ENUM | author / reviewer / command / re-review / reconcile |
| status | ENUM | pending_ci / queued / running / partial / failed / posted / ci-failed / skipped |
| attempt | INT | Retry attempt count |
| review_id | INT NULL | GitHub review id when posted |
| artifact_dir | TEXT | `.runs/<id>/` path |
| created_at / updated_at | DATETIME | Timestamps |

**Unique constraint**: `(owner, repo, pr_number, head_sha, model_alias)` — enforced transactionally with `INSERT OR IGNORE` (REQ-004, REQ-NF-005, ARCH-011).

**Sources**: spec.md Key Entities; REQ-004, REQ-015, REQ-IF-005, SYS-012.

### ModelAlias (→ SQLite `model_aliases`)

| Field | Type | Notes |
|-------|------|-------|
| alias | TEXT PK | e.g. `free`, `go`, `gemini` |
| provider | TEXT | opencode / opencode-go / google-one |
| model | TEXT | Provider model name |
| auth_ref | TEXT | **Env var name only** — never the key (REQ-NF-004) |
| enabled | BOOL | Disabled aliases (e.g. `gemini`) are not selectable |
| is_default | BOOL | Default model |

**Sources**: spec.md Key Entities; REQ-013, REQ-IF-005, SYS-010, ARCH-010.

### RepoConfig (→ SQLite `repo_config`)

| Field | Type | Notes |
|-------|------|-------|
| owner | TEXT | Repo owner |
| repo | TEXT | Repo name |
| verdict_policy | ENUM | Always `comment` (REQ-012) |
| default_model | TEXT | Per-repo default model alias |
| scope_rules | JSON | Per-repo scope-rule overrides (REQ-008) |
| enabled | BOOL | Managed repo on/off; denylist subtracts within it |

**Sources**: spec.md Key Entities; REQ-003, REQ-008, REQ-012, REQ-IF-005, SYS-013.

### CachedRepo (Clone Cache Metadata)

| Field | Type | Notes |
|-------|------|-------|
| owner | TEXT | Repo owner |
| name | TEXT | Repo name |
| path | TEXT | Checkout path in cache |
| last_used_at | DATETIME | LRU eviction key (REQ-005) |
| size_bytes | INT | For disk-cap accounting |

**Sources**: spec.md Key Entities; REQ-005, SYS-004, ARCH-004.

## SQLite Schema (REQ-IF-005)

```
review_runs  (id PK, owner, repo, pr_number, head_sha, model_alias, trigger,
              status, attempt, review_id, artifact_dir, created_at, updated_at,
              UNIQUE (owner, repo, pr_number, head_sha, model_alias))
repos        (owner, name, repo_status, verdict_policy, default_model, enabled,
              PRIMARY KEY (owner, name))
model_aliases(alias PK, provider, model, auth_ref, enabled, is_default)
repo_config  (owner, repo, verdict_policy, default_model, scope_rules,
              PRIMARY KEY (owner, repo))
```

Migrations run at boot (ATP-IF-005-A1 / SCN-IF-005-A1). WAL mode for cross-worker consistency (ARCH-003).

## Derived From System Design

| Data construct | System source |
|----------------|---------------|
| `review_runs` table | SYS-012 State Store, SYS-003 Review Coordinator (dedup) |
| `repos` / `repo_config` tables | SYS-013 Config Manager, REQ-IF-004 |
| `model_aliases` table | SYS-010 Model Registry |
| Clone cache metadata | SYS-004 Repo Clone Cache |
| Run artifacts (`.runs/`) | SYS-014 Runtime & Observability (REQ-NF-007) |
