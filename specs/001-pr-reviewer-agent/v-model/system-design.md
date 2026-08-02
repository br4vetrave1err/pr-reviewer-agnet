# System Design: GitHub PR Review Agent

**Feature Branch**: `001-pr-reviewer-agent`
**Created**: 2026-08-01
**Status**: Approved
**Source**: `specs/001-pr-reviewer-agent/v-model/requirements.md`

### Overview

The system is a long-running Docker service. Webhook events enter through a signed HTTP endpoint (`/api/webhook`), are filtered to PRs where the configured self-account is author/reviewer or `check_run`/`workflow_run` CI completion events, and enqueue a ReviewRun for each new head SHA (dedup keyed on repo, PR, head, model). A single worker executes each run against an isolated clone workspace (`workspace_cache_dir`), but only after the CI gate passes: it waits for gating CI runs on the head to complete; a gating failure posts a root-cause diagnosis comment instead of a review. On a green head the pipeline loads `specs/<owner>/<repo>/` docs, validates PR scope and test compliance (discovery only — the container never runs the repo's test suites), runs gitleaks plus the LLM security review inside the review session, and invokes opencode as a one-off `opencode run` CLI subprocess with the defined `agent_skill_set` (`/code-review` base, `/diagnosing-bugs`, `/resolving-merge-conflicts`) and a selected model alias. Results are assembled into a formal GitHub review posted as event `COMMENT` with an idempotency marker. All state (dedup, config, run records) lives in SQLite and YAML config; every run is logged and retried with backoff, and a periodic reconcile sweep re-enqueues open PRs whose head lacks a posted review.

## ID Schema

- **System Component**: `SYS-NNN` — sequential identifier for each component
- **Parent Requirements**: Comma-separated `REQ-NNN` list per component (many-to-many)
- Example: `SYS-003` with Parent Requirements `REQ-004, REQ-014` — the coordinator satisfies both

## Decomposition View (IEEE 1016 §5.1)

| SYS ID | Name | Description | Parent Requirements | Type |
|--------|------|-------------|---------------------|------|
| SYS-001 | Webhook Receiver | HTTPS endpoint `/api/webhook`; verifies `X-Hub-Signature-256` HMAC; ACKs within 2s and hands payloads to the pipeline asynchronously. Exposes `POST /api/reviews/{run_id}/approve` API approval endpoint and `POST /api/slack/events` / `POST /api/slack/interactivity` 2-way Slack endpoints. | REQ-001, REQ-021, REQ-025, REQ-IF-002, REQ-NF-002 | Service |
| SYS-002 | Trigger Filter | Decides whether a PR or CI completion warrants review: self-account is author (`opened`/`ready_for_review`/`synchronize` incl. self-authored Draft PRs), requested reviewer, or `@review` / `@review approve` command; applies `repo_config` + denylist; logs skips. | REQ-001, REQ-002, REQ-003, REQ-018, REQ-021 | Module |
| SYS-003 | Review Coordinator | Owns the queue, concurrency 1, CI-gate wait (`pending_ci`), staged review preview gate (`pending_approval`), dedup per (repo, PR, head SHA, model), re-review on new SHA, stale review invalidation on push / 24h expiration, retry with backoff, idempotency-marker checks, partial-report handling, and the reconcile sweep. | REQ-004, REQ-010, REQ-014, REQ-020, REQ-023, REQ-NF-005, REQ-NF-006 | Subsystem |
| SYS-004 | Repo Clone Cache | Isolated per-repo clone workspace inside container (`workspace_cache_dir`); plain `git clone` over HTTPS using the PAT, incremental fetch to head, and LRU eviction. | REQ-005 | Library |
| SYS-005 | Docs Context Loader | Reads this repo's `specs/<owner>/<repo>/` tree; maps `<owner>/<repo>/` folders; degrades gracefully when a folder is absent. | REQ-006, REQ-IF-006 | Module |
| SYS-006 | Review Executor | Runs opencode as a one-off `opencode run` CLI subprocess with `cwd` at the checkout (read-only), repo `AGENTS.md` + `.opencode/` skills, vendored `.agents/skills/`, docs, resolved model alias, and defined `agent_skill_set`; parses the structured-JSON result. | REQ-007, REQ-017, REQ-IF-003, REQ-CN-003 | Subsystem |
| SYS-007 | PR Scope & Test Compliance Validator | Validates change scope boundaries (modified files match PR title/body/issues) and verifies test case additions adhere to repo rules in `AGENTS.md` / `.opencode/`. Discovery + compliance only — no test execution. | REQ-008 | Library |
| SYS-008 | Security Scan & CI Failure Debugger | Runs security scans (gitleaks secrets + LLM review in-session) on green heads and fetches/debugs GitHub CI/CD failure logs on `check_run`/`workflow_run` events to produce a root-cause diagnosis comment for failed gates. | REQ-009, REQ-010 | Service |
| SYS-009 | Report Publisher | Reads the assembled review, posts the formal GitHub review (summary + CI status + scope/test findings + security results + model used, inline comments) with event `COMMENT` or `APPROVE` for approved self-authored draft PRs (plus `markPullRequestReadyForReview` promotion), and updates run state. | REQ-011, REQ-012, REQ-022, REQ-IF-001 | Service |
| SYS-010 | Model Registry | Maps model aliases to provider + model + auth reference (`free` → opencode, `go` → opencode-go; `gemini` disabled); reads the single application-layer model definition (REQ-016); validates aliases and resolves default. | REQ-013, REQ-016 | Module |
| SYS-011 | Comment Command Interpreter | Parses PR comment commands (`@review --model <alias>`, `@review approve`); validates aliases; replies with help on unknown/malformed commands. | REQ-013, REQ-021 | Module |
| SYS-012 | State Store | SQLite database implementing the documented schema (`review_runs`, `repos`, `model_aliases`, `repo_config`); transactional dedup and crash recovery. | REQ-IF-005, REQ-NF-005 | Library |
| SYS-013 | Config Manager | Loads and validates `config.yaml` (providers, `repo_config`, denylist, defaults, concurrency, CI-gate settings, retry policy, docs location, agent skill set); exposes typed access. | REQ-IF-004, REQ-016, REQ-CN-001 | Library |
| SYS-014 | Runtime & Observability | Process lifecycle (graceful shutdown, restart-safe recovery), dynamic ngrok URL discovery & webhook auto-registration, structured JSON logs, Slack Block Kit webhook & 2-way event notifications (`SLACK_WEBHOOK_URL`), persisted run records, GitHub rate-limit handling, secret hygiene, and read-only enforcement. | REQ-015, REQ-019, REQ-024, REQ-025, REQ-NF-001, REQ-NF-003, REQ-NF-004, REQ-NF-007, REQ-CN-002, REQ-CN-004 | Subsystem |

## Dependency View (IEEE 1016 §5.2)

| Source | Target | Relationship | Failure Impact |
|--------|--------|-------------|----------------|
| SYS-001 | SYS-002 | Calls | Rejected/malformed payloads are logged; no review is enqueued. |
| SYS-002 | SYS-003 | Calls | Filter failure blocks enqueueing; PR is skipped and logged. |
| SYS-011 | SYS-003 | Calls | Command cannot trigger a re-review; user sees no response (logged). |
| SYS-003 | SYS-012 | Reads/Writes | Dedup/state loss ⇒ duplicate reviews or lost runs; SQLite is the single source of truth. |
| SYS-003 | SYS-013 | Reads | Config failure at boot ⇒ service refuses to start (fail-closed). |
| SYS-003 | SYS-004 | Calls | Workspace clone failure aborts the run; retried with backoff then partial-report. |
| SYS-003 | SYS-005 | Calls | Docs failure degrades to no-docs run (recorded), never aborts. |
| SYS-003 | SYS-006 | Calls | opencode CLI subprocess failure retried; repeated failure ⇒ partial-report comment. |
| SYS-006 | SYS-007 | Calls | Scope/test validation warning recorded in review payload; never aborts run. |
| SYS-006 | SYS-008 | Calls | Security scan or CI log fetch failure degrades that phase; other phases still run. |
| SYS-006 | SYS-010 | Reads | Unknown model alias ⇒ run refuses with a help reply (REQ-013). |
| SYS-006 | SYS-014 | Reads | Rate-limit/middleware failure retries the whole run. |
| SYS-009 | SYS-012 | Writes | Posting without state update ⇒ duplicate posts on retry; mitigated by posting-transaction. |
| SYS-014 | SYS-001…SYS-013 | Uses | Logging/observability outage must not crash the pipeline (log-loss tolerated, not blocking). |

### Dependency Diagram

```text
            GitHub (webhooks: pull_request, issue_comment, check_run, workflow_run)
                     │ HTTPS (signed, HMAC)
                     ▼
             SYS-001 Webhook Receiver ──► SYS-002 Trigger Filter ──► SYS-003 Review Coordinator
                     │                                                      │  (queue, dedup, CI gate,
                     │                                              ┌───────┼───────┐  retry)
              SYS-011 Comment Command Interpreter ◄────────────────┘       │       │
                     ▲                                                      ▼       ▼
                     │                                        SYS-004 Clone Cache   SYS-012 State Store (SQLite)
             GitHub comments                             SYS-005 Docs Loader (specs/)   SYS-013 Config (YAML)
                                                                      │
                                                                      ▼
                                                         SYS-006 Review Executor (opencode run CLI subprocess)
                                                           ├──► SYS-007 PR Scope & Test Compliance Validator
                                                           ├──► SYS-008 Security Scan & CI Failure Debugger
                                                           └──► SYS-010 Model Registry
                                                                      │
                                                                      ▼
                                                         SYS-009 Report Publisher ──► GitHub (COMMENT review + inline)
                                                                      │
                                                           SYS-014 Runtime & Observability (logs, .runs/, rate limit, secrets)
```

## Interface View (IEEE 1016 §5.3)

### External Interfaces

| Component | Interface Name | Protocol | Input | Output | Error Handling |
|-----------|---------------|----------|-------|--------|----------------|
| SYS-001 | GitHub Webhook | HTTPS POST `/api/webhook` | JSON delivery (`pull_request`, `issue_comment`, `check_run`, `workflow_run`), `X-Hub-Signature-256` header, `X-GitHub-Event` | HTTP 200/204 ACK | 401 on bad signature; 5xx on transient; never ACK before signature check |
| SYS-009 | GitHub REST API | HTTPS (GitHub REST API, PAT `repo` scope) | PR reads, diffs, CI check runs & job logs, review payloads, comments, webhook register/re-point | Review/comment/log payload IDs, status | Retry on 403/429 with backoff; 404 ⇒ resource missing ⇒ skip/warn |
| SYS-006 | OpenCode CLI | Subprocess (`opencode run <session prompt>`) | `cwd` = checkout, env with provider keys (auth_ref), prompt args, vendored/repo skills | Machine-readable result (structured JSON) or non-zero exit | Non-zero exit classified into retryable vs. reportable |
| SYS-007 | PR Scope & Test Rules | Internal AST / Rule Checkers | Diff list, PR title/body/issues, repo `AGENTS.md` / `.opencode/` rules | Scope violation list, test compliance findings | Non-blocking warnings in review summary |
| SYS-008 | Scanner & CI Debugger | Subprocess / GitHub API | gitleaks args + in-session LLM security review + GitHub CI job log endpoint | Machine-readable security reports & CI root-cause diagnostics | Scanner/log failure ⇒ phase skipped and logged; never aborts |
| SYS-005 | Docs tree (`specs/<owner>/<repo>/`) | File I/O in this repo | `owner/repo` key | Docs file list + content | Unreadable ⇒ no-docs run, recorded |
| SYS-013 | Config file | File I/O | `config.yaml` | Validated config object | Invalid ⇒ fail-closed at boot |

### Internal Interfaces

| Source | Target | Interface Name | Protocol | Data Format | Error Handling |
|--------|--------|---------------|----------|-------------|----------------|
| SYS-003 | SYS-012 | State read/write | In-process (Python `sqlite3`/`aiosqlite`, WAL) | Typed records (ReviewRun, CachedRepo) | Transactions; unique index on (repo, pr, head, model) |
| SYS-006 | SYS-010 | Model resolve | In-process | ModelAlias record | Unknown alias returned as typed error |
| SYS-006 | SYS-009 | Review payload | In-process | Assembled review object (summary + CI diagnostics + scope/test findings) | Invalid payload ⇒ internal error, retried |
| SYS-014 | All | Log stream | In-process | Structured JSON lines | Log failure non-blocking |

## Data Design View (IEEE 1016 §5.4)

| Entity | Component | Storage | Protection at Rest | Protection in Transit | Retention |
|--------|-----------|---------|-------------------|-----------------------|-----------|
| ReviewRun | SYS-012 | SQLite | Filesystem perms; DB volume not committed | n/a (local) | Kept; pruned by `keep_last_n_runs` config |
| CachedRepo | SYS-012 | SQLite | Filesystem perms | n/a (local) | Evicted by LRU/disk cap |
| CachedRepo contents | SYS-004 | Filesystem (`/var/agent_cache/repos/`) | Plain HTTPS clone via PAT; no secrets in checkout | HTTPS | LRU eviction against disk cap |
| ModelAlias | SYS-012 | SQLite + config | n/a (no secrets stored, only auth *reference*) | n/a | Config-managed |
| ReviewRun artifacts | SYS-014 | Filesystem (`.runs/<id>/`) | Filesystem perms | n/a (local) | Pruned with run records |
| Secrets (keys/tokens) | SYS-014 | Environment / mounted secret file | Never written to disk by the app | TLS to GitHub/providers | Rotated out of band |

---

## Coverage Summary

| Metric | Count |
|--------|-------|
| Total System Components (SYS) | 14 (14 active, 0 deprecated, 0 suspect) |
| Total Parent Requirements Covered | 34 / 34 (100%) (active items only) |
| Components per Type | Subsystem: 4 \| Module: 4 \| Service: 4 \| Library: 2 |
| **Forward Coverage (REQ→SYS)** | **100%** |

## Derived Requirements

None — all components trace to existing requirements.

## Glossary

| Term | Definition |
|------|-----------|
| ReviewRun | One review attempt for a (repo, PR, head SHA, model). |
| Head SHA | The commit SHA the PR source branch currently points at. |
| CI Failure Diagnostic | Root-cause analysis of failed GitHub CI/CD job logs with suggested fix. |
| PR Scope Boundary | Validation that modified files strictly pertain to PR title/body/linked issues. |
| LRU eviction | Least-recently-used eviction of cached clones against a disk cap. |
| Partial report | A comment stating what ran and what did not when a review cannot complete. |
