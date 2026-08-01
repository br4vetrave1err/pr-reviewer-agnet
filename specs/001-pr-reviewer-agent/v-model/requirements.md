# V-Model Requirements Specification: GitHub PR Review Agent

**Feature Branch**: `001-pr-reviewer-agent`
**Created**: 2026-08-01
**Status**: Approved
**Source**: `specs/001-pr-reviewer-agent/spec.md`

## Overview

A continuously-running Docker service that acts as a PR review agent for a single configured GitHub account. Whenever the account opens a PR (or is tagged as a requested reviewer) on any repo listed in `repo_config`, the agent clones the repo into a persistent cache, loads per-repo docs from this repo's `specs/<owner>/<repo>/` tree, performs security analysis (gitleaks secrets scan + LLM review) and PR scope/test-compliance validation, then runs opencode headlessly in the clone (as a one-off `opencode run` subprocess, with vendored and repo-scoped skills) to produce a detailed formal GitHub review. Reviews are gated on CI (green heads only; failing CI gets a diagnosis comment), deduplicated per (repo, PR, head SHA, model), re-run on new commits, use pluggable model providers selected via config aliases or a per-PR comment command, and are always posted as `COMMENT` with advisory verdict prose. A periodic reconcile sweep and an idempotency marker guard against missed events and duplicate posts.

## Requirements

### Functional Requirements

| ID | Description | Priority | Rationale | Verification Method |
|----|-------------|----------|-----------|---------------------|
| REQ-001 | The system SHALL receive GitHub webhook events (`pull_request` actions `opened`/`ready_for_review`/`synchronize`/`review_requested`, `issue_comment` action `created`, `check_run`/`workflow_run` action `completed`) and SHALL verify the `X-Hub-Signature-256` HMAC before processing any payload; unsupported events SHALL be ignored silently. | P1 | Prevents forged events from triggering reviews. | Test |
| REQ-002 | The system SHALL trigger a review for a PR when the configured GitHub account is the PR author (action `opened` or `ready_for_review`), when the account is added as a requested reviewer (action `review_requested`), or when the account comments `@review --model <alias>`. | P1 | Both triggers were explicitly requested by the user. | Test |
| REQ-003 | The system SHALL review only repos listed in `repo_config` (webhook registration is the allow) and SHALL apply a `denylist` that subtracts within it; SHALL log skipped PRs with the reason. | P1 | Lets the user silence noisy repos. | Test |
| REQ-004 | The system SHALL deduplicate reviews per (owner, repo, PR number, head SHA, model alias): no duplicate review for the same head+model, and an automatic re-review when a new head SHA is pushed (`synchronize`). | P1 | Avoids duplicate/SPAM reviews while keeping reviews current. | Test |
| REQ-005 | The system SHALL maintain an isolated clone cache inside the container (`workspace_cache_dir`), seeded by plain `git clone` over HTTPS using the PAT, updated incrementally, and evicted by LRU against a disk cap. | P2 | Isolated cache without host interference or network churn. | Test |
| REQ-006 | The system SHALL load per-repo documentation from this repo's `specs/<owner>/<repo>/` tree and SHALL pass it to the agent as review context; a missing folder SHALL result in a review-without-docs that records the degradation. | P1 | User supplies codebase docs as review context; graceful when absent. | Test |
| REQ-007 | The system SHALL run the review agent by spawning a one-off `opencode run` subprocess in the checkout (read-only), with repo `AGENTS.md`, `.opencode/` skills, vendored `.agents/skills/`, and minimal defined `agent_skill_set`; a structured-JSON output contract is used, with no HTTP daemon. | P1 | CLI subprocess invocation with repo conventions and self-contained skills. | Test |
| REQ-008 | The system SHALL perform PR scope validation (ensuring changed files strictly pertain to PR details/linked issues) and test compliance verification (test additions matching repo rules in `AGENTS.md` / `.opencode/`). The container SHALL NOT execute the target repo's test suites; "test results" are CI status plus compliance findings. | P1 | Enforces change discipline and test rule adherence without re-running CI locally. | Test |
| REQ-009 | The system SHALL run security analysis covering: a full-checkout secrets scan (`gitleaks`) and an LLM security review of the changed files (inside the single `/code-review` session). | P1 | Security analysis of each PR is a core user requirement. | Test |
| REQ-010 | The system SHALL gate reviews on CI (Rule B): wait for all gating `check_run`/`workflow_run` runs on the head to complete; review and scans proceed only if none failed. A failing gate SHALL produce a root-cause diagnosis comment (fetch failure logs via GitHub API), with no review and no scans. | P2 | Diagnoses CI/CD failures without locally re-running tests. | Inspection |
| REQ-011 | The system SHALL post a formal GitHub review containing a detailed summary (findings, CI failure diagnostics, scope/test adherence, security results, model used) and inline comments. | P1 | "Detailed message for updates" is the user-facing output. | Test |
| REQ-012 | The review SHALL be posted with event `COMMENT`; the advisory verdict (approve / comment / request-changes) SHALL be expressed as prose in the summary body. Formal `APPROVE`/`REQUEST_CHANGES` review events SHALL never be used. | P2 | Advisory by default; no hard-blocking. | Demonstration |
| REQ-013 | The system SHALL support pluggable model providers with config aliases (`free` → `opencode`, `go` → `opencode-go`; `gemini` defined but disabled) and SHALL honor a per-PR override via the comment command `@review --model <alias>`; an unknown or disabled alias SHALL produce a reply listing valid aliases and SHALL NOT run. | P1 | Model selection is an explicit user requirement. | Test |
| REQ-014 | The system SHALL retry transient failures (GitHub API, network, model provider) with exponential backoff, and SHALL post a partial-report comment when a review cannot complete. | P1 | Prevents silent failures; keeps the PR informed. | Test |
| REQ-015 | The system SHALL record every run (trigger, inputs, head SHA, model alias, outcome, timestamps) in structured logs and SHALL persist a run record per completed or failed review. | P2 | Auditability and debugging. | Inspection |
| REQ-016 | Model provider definitions SHALL be defined once in the application layer (a single `providers` + `default_model` config section) and SHALL be switchable by configuration change only. | P2 | Model definition and runtime fallback. | Test |
| REQ-017 | The review agent SHALL be given a defined agent skill set as the base for reviewing changes: `/code-review` (base skill), `/diagnosing-bugs`, and `/resolving-merge-conflicts`. | P2 | Minimal self-contained skill set. | Test |

### Non-Functional Requirements

| ID | Description | Priority | Rationale | Verification Method |
|----|-------------|----------|-----------|---------------------|
| REQ-NF-001 | The system SHALL run as a long-lived Docker service with graceful shutdown and restart-safe state recovery. | P1 | Continuous execution model. | Analysis |
| REQ-NF-002 | The webhook endpoint SHALL acknowledge delivery within 2 seconds; all review processing SHALL happen asynchronously via a queue. | P1 | GitHub expects fast webhook ACKs; processing is slow. | Test |
| REQ-NF-003 | The system SHALL respect GitHub API rate limits (single PAT, backoff and retry on 403/429, exponential backoff with jitter). | P2 | Prevents token suspension during bursts. | Test |
| REQ-NF-004 | The system SHALL keep all secrets (PAT, webhook secret, model provider keys) out of the repository, out of logs, and out of review output; secrets SHALL be supplied via a gitignored `.env` delivered with `env_file`, and the container SHALL construct opencode's `auth.json` from the `OPENCODE_GO_TOKEN` value at boot. | P1 | The agent reviews other people's code with elevated tokens. | Inspection |
| REQ-NF-005 | The queue and SQLite state SHALL provide crash-safe, at-least-once, idempotent processing such that a crash mid-run leaves no orphaned lock and never double-posts a review; idempotency SHALL be anchored to the GitHub-side comment marker `_Reviewed by PR Review Agent · run <run_id>_`, with DB state advisory. | P1 | Reliability of an unattended continuous service. | Test |
| REQ-NF-006 | The system SHALL bound concurrency (default: 1 concurrent review run — serial execution) and SHALL queue excess work. | P2 | Bounds CPU, disk, and GitHub API consumption. | Test |
| REQ-NF-007 | Every review run SHALL emit structured JSON logs (trigger, repo, PR, head SHA, model, phases, outcome) persisted to `.runs/`. | P2 | Debugging and audit trail. | Inspection |

### Interface Requirements

| ID | Description | Priority | Rationale | Verification Method |
|----|-------------|----------|-----------|---------------------|
| REQ-IF-001 | The system SHALL use the GitHub REST API (PAT with `repo` scope) to read PRs, PR diffs, CI/CD check logs, create comments, submit reviews, and manage per-repo webhooks. | P1 | Primary external contract. | Test |
| REQ-IF-002 | The webhook endpoint SHALL accept `POST` JSON payloads at `/api/webhook` and SHALL reject invalid signatures with HTTP 401. | P1 | Trigger channel contract. | Test |
| REQ-IF-003 | The system SHALL invoke the opencode CLI as a non-interactive subprocess (`opencode run <session prompt>`) with a defined structured-JSON output contract; no HTTP daemon. | P1 | OpenCode execution boundary. | Test |
| REQ-IF-004 | Configuration SHALL be a YAML file (`config.yaml`) defining provider aliases, `repo_config`, denylist, defaults, concurrency, CI-gate settings, and docs location. | P1 | Central user-visible configuration surface. | Test |
| REQ-IF-005 | The SQLite state database SHALL expose a documented schema: `review_runs`, `repos`, `model_aliases`, `repo_config`. | P1 | State contract for dedup, re-review, and recovery. | Test |
| REQ-IF-006 | The docs SHALL live in this repo's `specs/<owner>/<repo>/` tree, containing markdown docs consumed as review context. | P2 | Docs mapping contract. | Inspection |

### Constraint Requirements

| ID | Description | Priority | Rationale | Verification Method |
|----|-------------|----------|-----------|---------------------|
| REQ-CN-001 | The system MUST run inside Docker on the user's machine as a compose stack (app + `ngrok/ngrok` sidecar), with the GitHub webhook URL pointing at the tunnel's current public URL (self-healed on change). | P1 | Deployment & reachability constraint. | Inspection |
| REQ-CN-002 | The container image MUST include Python 3.11+, the opencode CLI (npm-installed), git, and gitleaks. | P1 | Container toolchain constraint. | Inspection |
| REQ-CN-003 | The review agent SHALL use self-contained `agent_skill_set` without requiring external global skill mounts. | P2 | Minimal skill architecture constraint. | Inspection |
| REQ-CN-004 | The agent MUST NOT push or commit to any reviewed repository; all review operations are read-only with respect to the target repo. | P1 | Read-only safety constraint. | Inspection |

## Assumptions

- The agent operates as a single configured GitHub account via a classic PAT (`repo` scope); no App installation.
- The review skills are defined within `agent_skill_set` (`/code-review`, `/diagnosing-bugs`, `/resolving-merge-conflicts`) and vendored into the repo's `.agents/skills/`.
- Docs context comes from this repo's `specs/<owner>/<repo>/` tree.
- OpenCode runs as a one-off CLI subprocess (`opencode run`); provider keys are supplied via `auth.json` built at boot from `.env`.
- CI/CD workflow runs execute repository test suites automatically on GitHub; the agent inspects CI status and failure logs via GitHub API and never re-runs them locally.
- The ngrok tunnel provides webhook reachability from GitHub.

## Dependencies

- GitHub REST API + per-repo webhooks (PAT) — external.
- ngrok tunnel — external (webhook reachability).
- opencode CLI + selected model providers (OpenCode Zen, OpenCode GO) — external.
- gitleaks CLI — external.
- This repo's `specs/` tree for docs context — internal.

## Glossary

| Term | Definition |
|------|-----------|
| Head SHA | The commit SHA the PR's source branch currently points at. |
| ReviewRun | One review attempt for a (repo, PR, head SHA, model). |
| CI gate (Rule B) | Reviews run only after all gating CI runs on a head complete; a gating failure yields a diagnosis comment instead. |
| Partial report | A comment posted when a review cannot complete, stating what ran and what did not. |
| Model alias | A config name mapping to a provider + model (e.g. `free`, `go`). |
| specs tree | This repo's `specs/<owner>/<repo>/` markdown docs consumed as review context. |
| Idempotency marker | The `_Reviewed by PR Review Agent · run <run_id>_` comment footer that anchors duplicate-prevention. |
| Managed repo | A repo listed in `repo_config` — the allow for webhook registration and review. |

---

**Total Requirements**: 34 (34 active, 0 deprecated)
**By Priority**: P1: 22 | P2: 12 | P3: 0
**By Verification Method**: Test: 22 | Inspection: 9 | Analysis: 1 | Demonstration: 2
