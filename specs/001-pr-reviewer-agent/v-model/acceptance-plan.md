# Acceptance Test Plan: GitHub PR Review Agent

**Feature Branch**: `001-pr-reviewer-agent`
**Created**: 2026-08-01
**Status**: Approved
**Source**: `specs/001-pr-reviewer-agent/v-model/requirements.md`

## Overview

This document defines the Acceptance Test Plan for the GitHub PR Review Agent. Every requirement in `requirements.md` has at least one Test Case (ATP), and every Test Case has at least one executable User Scenario (SCN) in BDD format (Given/When/Then).

## ID Schema

- **Test Case**: `ATP-{NNN}-{X}` â€” where NNN matches the parent REQ, X is a letter suffix (A, B, C...)
- **Scenario**: `SCN-{NNN}-{X}{#}` â€” nested under the parent ATP, with numeric suffix (1, 2, 3...)
- Example: `SCN-001-A1` â†’ Scenario 1 of Test Case A validating REQ-001

## Acceptance Tests

### Requirement Validation: REQ-001 (Webhook signature verification)

#### Test Case: ATP-001-A (Valid and invalid signatures)

**Description:** Webhook payloads with a valid HMAC are processed; payloads with a bad or missing signature are rejected with 401 and never processed.

* **User Scenario: SCN-001-A1**
  * **Given** a signed `pull_request` webhook delivery with a correct `X-Hub-Signature-256`
  * **When** the payload is delivered to the webhook endpoint
  * **Then** the endpoint returns 200 and the event is processed
* **User Scenario: SCN-001-A2**
  * **Given** a webhook delivery whose HMAC does not match the secret
  * **When** the payload is delivered to the webhook endpoint
  * **Then** the endpoint returns 401 and no event processing occurs

#### Test Case: ATP-001-B (Signature-independent fast ACK)

**Description:** Acknowledging a valid delivery does not depend on the (slow) review pipeline.

* **User Scenario: SCN-001-B1**
  * **Given** a valid webhook delivery
  * **When** the payload is delivered
  * **Then** the endpoint acknowledges within 2 seconds regardless of queue backlog

---

### Requirement Validation: REQ-002 (Trigger conditions)

#### Test Case: ATP-002-A (Author and reviewer triggers)

**Description:** A review is enqueued when I open a PR, mark a draft ready, or am added as a requested reviewer.

* **User Scenario: SCN-002-A1**
  * **Given** I open a PR on an allowed repo
  * **When** the `pull_request` `opened` event arrives
  * **Then** a review run is enqueued for that PR
* **User Scenario: SCN-002-A2**
  * **Given** I am added as a requested reviewer on a PR
  * **When** the `review_requested` event arrives
  * **Then** a review run is enqueued for that PR
* **User Scenario: SCN-002-A3**
  * **Given** a PR event where I am neither author nor requested reviewer
  * **When** the event arrives
  * **Then** no review is enqueued and the skip is logged with a reason

---

### Requirement Validation: REQ-003 (Managed repos + denylist)

#### Test Case: ATP-003-A (Managed-repo gating)

**Description:** PRs from repos not listed in `repo_config` (or denylisted) never trigger reviews; webhook registration is the allow.

* **User Scenario: SCN-003-A1**
  * **Given** a repo not listed in `repo_config`
  * **When** a triggering event arrives
  * **Then** no review is created and the skip reason is logged
* **User Scenario: SCN-003-A2**
  * **Given** a repo listed in `repo_config` and in the denylist
  * **When** a triggering event arrives
  * **Then** no review is created even though the trigger matched

---

### Requirement Validation: REQ-004 (Dedup and re-review)

#### Test Case: ATP-004-A (No duplicates, re-review on new head)

**Description:** One review per (repo, PR, head SHA, model); new head SHAs produce a fresh review; a different model at the same head is a distinct run.

* **User Scenario: SCN-004-A1**
  * **Given** a review was already posted for head SHA-A with model `free`
  * **When** an identical event for SHA-A arrives again
  * **Then** no duplicate review is posted
* **User Scenario: SCN-004-A2**
  * **Given** a review was posted for SHA-A
  * **When** a `synchronize` event reports head SHA-B
  * **Then** a new review is posted for SHA-B

---

### Requirement Validation: REQ-005 (Persistent clone cache)

#### Test Case: ATP-005-A (Clone, update, evict)

**Description:** Repos are cloned once, updated incrementally, and evicted by LRU under a disk cap.

* **User Scenario: SCN-005-A1**
  * **Given** a repo with no cached clone
  * **When** a review for it is enqueued
  * **Then** a full clone is created in the cache
* **User Scenario: SCN-005-A2**
  * **Given** a cached clone and a later head SHA
  * **When** a review for the new SHA is enqueued
  * **Then** the clone is updated incrementally (fetch), not re-cloned
* **User Scenario: SCN-005-A3**
  * **Given** the cache exceeds the disk cap
  * **When** a new clone is required
  * **Then** least-recently-used clones are evicted until under the cap

---

### Requirement Validation: REQ-006 (Docs context)

#### Test Case: ATP-006-A (Docs loaded; graceful degradation)

**Description:** Docs for the target repo are loaded from this repo's `specs/<owner>/<repo>/` tree; absence degrades gracefully.

* **User Scenario: SCN-006-A1**
  * **Given** a folder `owner/repo` exists under `specs/`
  * **When** a review for that repo runs
  * **Then** the docs are passed to the agent as review context
* **User Scenario: SCN-006-A2**
  * **Given** no folder exists for the repo under `specs/`
  * **When** a review for that repo runs
  * **Then** the review completes without docs and records the degradation

---

### Requirement Validation: REQ-007 (Repo and vendored skills)

#### Test Case: ATP-007-A (Skills availability)

**Description:** The agent runs with the repo's own skills/AGENTS.md plus the vendored `.agents/skills/` set.

* **User Scenario: SCN-007-A1**
  * **Given** a repo with a custom skill and an `AGENTS.md`
  * **When** the agent runs inside that repo's clone
  * **Then** the repo's skill is available to the agent
* **User Scenario: SCN-007-A2**
  * **Given** the vendored `.agents/skills/` directory in the container image
  * **When** the agent runs in the container
  * **Then** the vendored skills (`/code-review`, `/diagnosing-bugs`, `/resolving-merge-conflicts`) are available

---

### Requirement Validation: REQ-008 (Scope + test compliance validation)

#### Test Case: ATP-008-A (Compliance validated; suites NOT executed)

**Description:** PR scope boundaries and test-compliance are validated (discovery only). The container never executes the repo's test suites; test results come from CI status + compliance findings.

* **User Scenario: SCN-008-A1**
  * **Given** a PR whose changed modules have no matching test additions
  * **When** the compliance validator runs
  * **Then** the missing-coverage finding appears in the review
* **User Scenario: SCN-008-A2**
  * **Given** a PR adding tests that violate the repo's `AGENTS.md` conventions
  * **When** the compliance validator runs
  * **Then** the non-compliant test finding appears in the review
* **User Scenario: SCN-008-A3**
  * **Given** a PR whose gating CI ran green on GitHub
  * **When** the review is assembled
  * **Then** the review reports the CI status (no local test execution occurs)

---

### Requirement Validation: REQ-009 (Security analysis)

#### Test Case: ATP-009-A (Security phases executed)

**Description:** gitleaks secrets scan and the LLM security review (in-session) run and appear in the review.

* **User Scenario: SCN-009-A1**
  * **Given** a PR containing a hard-coded secret in a changed file
  * **When** the security pipeline runs on a green head
  * **Then** the secrets scan (full checkout) reports the finding and it appears in the review
* **User Scenario: SCN-009-A2**
  * **Given** changed files with a security-relevant change pattern
  * **When** the LLM security review runs inside the review session
  * **Then** a security assessment of the changed files is produced and appears in the review
* **User Scenario: SCN-009-A3**
  * **Given** a PR whose gating CI failed
  * **When** the CI gate resolves
  * **Then** no security scans run (a diagnosis comment is posted instead)

---

### Requirement Validation: REQ-010 (CI gate and failure diagnosis)

#### Test Case: ATP-010-A (Rule B gate + diagnosis comment)

**Description:** Reviews run only on green heads; a gating failure yields a root-cause diagnosis comment, never a review.

* **User Scenario: SCN-010-A1**
  * **Given** a head with no configured CI
  * **When** the settle window (75s) elapses
  * **Then** the run proceeds to review (no-CI bypass)
* **User Scenario: SCN-010-A2**
  * **Given** a head whose gating CI completes with a failure
  * **When** `check_run`/`workflow_run` reports `completed`
  * **Then** the agent fetches the failure logs, posts a diagnosis comment, and posts no review
* **User Scenario: SCN-010-A3**
  * **Given** a head whose gating CI never completes
  * **When** the 60-minute wait cap is reached
  * **Then** one "CI hasn't completed; no review run" comment is posted and the run is skipped

---

### Requirement Validation: REQ-011 (Formal review with summary + inline)

#### Test Case: ATP-011-A (Review posted with required content)

**Description:** A formal GitHub review contains a summary (findings, CI status, security results, scope/test compliance, model used) and inline comments.

* **User Scenario: SCN-011-A1**
  * **Given** a completed review run
  * **When** the report publisher submits the review
  * **Then** a formal review is posted with event `COMMENT` and a summary section including CI status, security results, scope/test-compliance findings, and the model used
* **User Scenario: SCN-011-A2**
  * **Given** a review run with at least one high-confidence finding on a changed line
  * **When** the report publisher submits the review
  * **Then** an inline comment is placed on that line
* **User Scenario: SCN-011-A3**
  * **Given** a posted terminal comment
  * **When** its body is inspected
  * **Then** it carries the idempotency marker `_Reviewed by PR Review Agent · run <run_id>_`

---

### Requirement Validation: REQ-012 (COMMENT review event, advisory verdict prose)

#### Test Case: ATP-012-A (Always COMMENT)

**Description:** Reviews are always posted with event `COMMENT`; the verdict is prose in the summary.

* **User Scenario: SCN-012-A1**
  * **Given** a completed review run
  * **When** the report publisher submits the review
  * **Then** the review event is `COMMENT` and does not hard-block the PR
* **User Scenario: SCN-012-A2**
  * **Given** a review with blocking-severity findings
  * **When** the report publisher submits the review
  * **Then** the summary states the advisory verdict in prose ("changes needed") and the event remains `COMMENT` (never `REQUEST_CHANGES`/`APPROVE`)

---

### Requirement Validation: REQ-013 (Model aliases and per-PR override)

#### Test Case: ATP-013-A (Model selection via comment command)

**Description:** `@review --model <alias>` selects the model; unknown aliases produce a help reply, not a run.

* **User Scenario: SCN-013-A1**
  * **Given** a configured enabled alias `go`
  * **When** I comment `@review --model go` on a PR
  * **Then** the review runs with the `go` provider (opencode-go) and the review states the model used
* **User Scenario: SCN-013-A2**
  * **Given** no override comment on a PR
  * **When** a review is triggered
  * **Then** the configured default model is used
* **User Scenario: SCN-013-A3**
  * **Given** a comment `@review --model nope` where `nope` is unknown, or `--model gemini` (disabled)
  * **When** the comment is parsed
  * **Then** a reply lists valid aliases and no review runs

---

### Requirement Validation: REQ-014 (Retry and partial report)

#### Test Case: ATP-014-A (Retries then partial report)

**Description:** Transient failures retry with backoff; non-completable reviews post a partial-report comment.

* **User Scenario: SCN-014-A1**
  * **Given** a transient GitHub API failure during a review
  * **When** the pipeline hits the failure
  * **Then** the action is retried with exponential backoff (3 attempts, 30s/2min) before failing
* **User Scenario: SCN-014-A2**
  * **Given** a review whose opencode run fails after all retries
  * **When** the pipeline exhausts retries
  * **Then** a partial-report comment is posted stating what ran and what did not, and the PR is not hard-blocked

---

### Requirement Validation: REQ-015 (Run records and structured logs)

#### Test Case: ATP-015-A (Every run recorded)

**Description:** Every run emits structured logs and a persisted run record.

* **User Scenario: SCN-015-A1**
  * **Given** a completed or failed review run
  * **When** the run finishes
  * **Then** a structured run record with trigger, inputs, head SHA, model, outcome, and timestamps is persisted to `.runs/`

---

### Requirement Validation: REQ-NF-001 (Long-running, restart-safe)

#### Test Case: ATP-NF-001-A (Continuous service with safe restart)

**Description:** The service runs continuously and recovers state across restarts without duplicate work.

* **User Scenario: SCN-NF-001-A1**
  * **Given** a running container with queued and running jobs
  * **When** the container is stopped and restarted
  * **Then** dedup state is preserved, orphaned `running` jobs are requeued, and no review is posted twice

---

### Requirement Validation: REQ-NF-002 (Fast webhook ACK)

#### Test Case: ATP-NF-002-A (Sub-2s acknowledgment)

**Description:** The endpoint ACKs within 2 seconds.

* **User Scenario: SCN-NF-002-A1**
  * **Given** a valid webhook delivery
  * **When** it is delivered
  * **Then** the endpoint ACKs within 2 seconds

---

### Requirement Validation: REQ-NF-003 (GitHub rate limits)

#### Test Case: ATP-NF-003-A (Backoff on 403/429)

**Description:** Rate-limit responses cause backoff and retry, never a crash.

* **User Scenario: SCN-NF-003-A1**
  * **Given** a GitHub API call returning 403/429
  * **When** the client makes the call
  * **Then** the client backs off with jitter and retries rather than failing immediately

---

### Requirement Validation: REQ-NF-004 (Secret hygiene)

#### Test Case: ATP-NF-004-A (No secrets in repo, logs, or output)

**Description:** Secrets never appear in the repo, logs, or review output.

* **User Scenario: SCN-NF-004-A1**
  * **Given** the service configured with a real PAT, webhook secret, and provider keys
  * **When** a review runs and its logs and review output are inspected
  * **Then** no secret value appears in logs, config files in the repo, or posted reviews

---

### Requirement Validation: REQ-NF-005 (Crash-safe idempotent processing)

#### Test Case: ATP-NF-005-A (At-least-once without double-post)

**Description:** A crash mid-run leaves no orphaned lock and never double-posts, anchored by the GitHub-side marker.

* **User Scenario: SCN-NF-005-A1**
  * **Given** a run killed between review submission and state update
  * **When** the service recovers
  * **Then** the idempotency marker on the already-posted comment prevents any duplicate review for the same (repo, PR, head, model)

---

### Requirement Validation: REQ-NF-006 (Bounded concurrency)

#### Test Case: ATP-NF-006-A (Max concurrent reviews)

**Description:** Concurrency is bounded (default 1 — serial execution); excess work is queued.

* **User Scenario: SCN-NF-006-A1**
  * **Given** ten PRs triggered at once and concurrency set to 1
  * **When** the scheduler runs
  * **Then** at most 1 review runs at a time and the rest are queued

---

### Requirement Validation: REQ-NF-007 (Structured logs per run)

#### Test Case: ATP-NF-007-A (JSON logs with run phases)

**Description:** Each run emits structured JSON log lines.

* **User Scenario: SCN-NF-007-A1**
  * **Given** a completed run
  * **When** its logs are inspected
  * **Then** JSON lines contain trigger, repo, PR, head SHA, model, phases, and outcome

---

### Requirement Validation: REQ-IF-001 (GitHub REST API usage)

#### Test Case: ATP-IF-001-A (REST operations succeed)

**Description:** PR reads, comment creation, and review submission use the GitHub REST API.

* **User Scenario: SCN-IF-001-A1**
  * **Given** a review ready to post
  * **When** the publisher calls the GitHub REST API
  * **Then** the review and comments are created via the API

---

### Requirement Validation: REQ-IF-002 (Webhook endpoint contract)

#### Test Case: ATP-IF-002-A (Endpoint rejects invalid signatures)

**Description:** The endpoint accepts POST JSON and rejects bad signatures with 401.

* **User Scenario: SCN-IF-002-A1**
  * **Given** a POST to `/api/webhook` with a bad signature
  * **When** the request arrives
  * **Then** the endpoint returns 401

---

### Requirement Validation: REQ-IF-003 (opencode CLI contract)

#### Test Case: ATP-IF-003-A (Headless opencode invocation)

**Description:** The system invokes opencode as a one-off `opencode run` CLI subprocess and parses its structured-JSON result.

* **User Scenario: SCN-IF-003-A1**
  * **Given** a checkout, docs, and a resolved model
  * **When** the workspace runner spawns `opencode run`
  * **Then** the runner receives a parseable JSON result or a classified non-zero exit

---

### Requirement Validation: REQ-IF-004 (Config file contract)

#### Test Case: ATP-IF-004-A (YAML config validated)

**Description:** Config is YAML, validated, and failures are fail-closed.

* **User Scenario: SCN-IF-004-A1**
  * **Given** a valid `config.yaml`
  * **When** the service boots
  * **Then** it starts with the configured providers, `repo_config`, and defaults
* **User Scenario: SCN-IF-004-A2**
  * **Given** an invalid `config.yaml`
  * **When** the service boots
  * **Then** it refuses to start with a clear error

---

### Requirement Validation: REQ-IF-005 (SQLite schema)

#### Test Case: ATP-IF-005-A (State schema honored)

**Description:** The SQLite database exposes `review_runs`, `repos`, `model_aliases`, `repo_config`.

* **User Scenario: SCN-IF-005-A1**
  * **Given** a fresh database
  * **When** migrations run at boot
  * **Then** the four documented tables exist with the documented unique constraints

---

### Requirement Validation: REQ-IF-006 (Specs docs layout contract)

#### Test Case: ATP-IF-006-A (owner/repo folder mapping)

**Description:** Docs are looked up by `<owner>/<repo>/` folders under this repo's `specs/` tree.

* **User Scenario: SCN-IF-006-A1**
  * **Given** a `specs/acme/webapp/` folder in this repo
  * **When** a review runs for repo `acme/webapp`
  * **Then** the docs under that folder are loaded as context

---

### Requirement Validation: REQ-CN-001 (Docker + tunnel deployment)

#### Test Case: ATP-CN-001-A (Docker compose brings it up)

**Description:** The service runs in Docker and is reachable via a tunnel.

* **User Scenario: SCN-CN-001-A1**
  * **Given** secrets provided via environment
  * **When** `docker compose up` runs on a clean machine
  * **Then** the service reaches "listening for webhooks" without manual steps

---

### Requirement Validation: REQ-CN-002 (Image toolchain)

#### Test Case: ATP-CN-002-A (Required CLIs present)

**Description:** The image contains a Python 3.11+ runtime with FastAPI, the opencode CLI, git, and gitleaks.

* **User Scenario: SCN-CN-002-A1**
  * **Given** the built container image
  * **When** the toolchain is probed inside it
  * **Then** the Python runtime and FastAPI, the opencode CLI, git, and gitleaks are all present and executable

---

### Requirement Validation: REQ-CN-003 (Vendored skills in image)

#### Test Case: ATP-CN-003-A (Skills directory present in image)

**Description:** The defined skill set (`/code-review`, `/diagnosing-bugs`, `/resolving-merge-conflicts`) is vendored into the image under `.agents/skills/`.

* **User Scenario: SCN-CN-003-A1**
  * **Given** a container built from the image
  * **When** the `.agents/skills/` directory is inspected inside the container
  * **Then** the three vendored skills are present and readable

---

### Requirement Validation: REQ-CN-004 (Read-only target repos)

#### Test Case: ATP-CN-004-A (No writes to reviewed repos)

**Description:** The agent never pushes or commits to a reviewed repo.

* **User Scenario: SCN-CN-004-A1**
  * **Given** a review run against a repo
  * **When** the run completes and the clone's refs and working tree are inspected
  * **Then** no new commits, branches, or pushes exist beyond the original clone/fetch

---

### Requirement Validation: REQ-016 (Single app-layer model definition, config-only switch)

#### Test Case: ATP-016-A (Define once, switch by config)

**Description:** Model providers are defined once in the application layer; switching the active model is a config change (e.g. when a provider's credits are exhausted), with no code change and no loss of per-PR overrides.

* **User Scenario: SCN-016-A1**
  * **Given** `providers` and `default_model` defined once in `config.yaml`
  * **When** a review runs without an override
  * **Then** the single configured default model is used
* **User Scenario: SCN-016-A2**
  * **Given** a provider's credits are exhausted
  * **When** I change `default_model` in `config.yaml` to another defined alias (no code change)
  * **Then** subsequent reviews use the new default
* **User Scenario: SCN-016-A3**
  * **Given** a new default set via config
  * **When** I comment `@review --model <other-alias>` on a PR
  * **Then** the per-PR override still takes precedence over the new default

---

### Requirement Validation: REQ-017 (Defined agent skill set)

#### Test Case: ATP-017-A (Agent skill set as review base)

**Description:** The review agent runs with a defined skill set — `/code-review` as the base, plus situational skills (`/diagnosing-bugs`, `/resolving-merge-conflicts`) — alongside the repo's own skills and the vendored `.agents/skills/` set in the image.

* **User Scenario: SCN-017-A1**
  * **Given** a review run with no bug or merge-conflict findings
  * **When** the agent reviews the changes
  * **Then** `/code-review` is used as the base review skill
* **User Scenario: SCN-017-A2**
  * **Given** a suspected bug in the changes
  * **When** the review finds the issue
  * **Then** `/diagnosing-bugs` is applied to investigate and explain the fix
* **User Scenario: SCN-017-A3**
  * **Given** a merge-conflict-style issue spotted in the changes
  * **When** the review processes it
  * **Then** `/resolving-merge-conflicts` is applied to explain how the conflict can be updated/resolved
* **User Scenario: SCN-017-A4**
  * **Given** the vendored `.agents/skills/` directory in the image
  * **When** a review runs
  * **Then** the defined skill set is available to the agent alongside the repo's own skills

---

### Requirement Validation: REQ-018 (Self-Authored Draft PR Ingress)

#### Test Case: ATP-018-A (Draft PR filtering by author)

**Description:** Draft PRs authored by the self-account are enqueued for review; Draft PRs from other authors are skipped until marked ready for review.

* **User Scenario: SCN-018-A1**
  * **Given** I open a Draft PR from my self-account
  * **When** the `pull_request` webhook event arrives
  * **Then** a review run is enqueued for my Draft PR
* **User Scenario: SCN-018-A2**
  * **Given** another user opens a Draft PR
  * **When** the `pull_request` webhook event arrives
  * **Then** the event is skipped with reason `not-self`

---

### Requirement Validation: REQ-019 (Slack Out-of-Band Notification)

#### Test Case: ATP-019-A (Slack Block Kit preview notification)

**Description:** When a review enters `pending_approval`, a Slack Block Kit formatted payload is sent to `SLACK_WEBHOOK_URL`.

* **User Scenario: SCN-019-A1**
  * **Given** a review analysis completes and enters `pending_approval`
  * **When** the notifier triggers
  * **Then** an HTTP POST request containing Slack Block Kit blocks, summary findings, and approval action links is delivered to `SLACK_WEBHOOK_URL`

---

### Requirement Validation: REQ-020 (Staged Preview Approval Gate)

#### Test Case: ATP-020-A (Staged review publication gate)

**Description:** Completed review findings are held in `pending_approval` state until explicit user confirmation is received.

* **User Scenario: SCN-020-A1**
  * **Given** a completed review run
  * **When** it enters `pending_approval`
  * **Then** no review comments are submitted to GitHub until explicit approval is granted

---

### Requirement Validation: REQ-021 (Dual-Channel Approval)

#### Test Case: ATP-021-A (Approval via GitHub comment or API endpoint)

**Description:** Staged reviews can be approved either by commenting `@review approve` on GitHub or calling `POST /api/reviews/{run_id}/approve`.

* **User Scenario: SCN-021-A1**
  * **Given** a pending staged review
  * **When** I comment `@review approve` on the PR ticket
  * **Then** the review state transitions from `pending_approval` to `posted` and comments are published to GitHub
* **User Scenario: SCN-021-A2**
  * **Given** a pending staged review
  * **When** an HTTP request is sent to `POST /api/reviews/{run_id}/approve`
  * **Then** the review is released and posted to GitHub

---

### Requirement Validation: REQ-022 (Draft PR Auto-Approval & Promotion)

#### Test Case: ATP-022-A (Draft PR auto-approval and ready-for-review promotion)

**Description:** Approving a staged review for a self-authored Draft PR submits the review with `event: APPROVE` and marks the PR as Ready for Review on GitHub.

* **User Scenario: SCN-022-A1**
  * **Given** an approved staged review for a self-authored Draft PR
  * **When** the publisher executes
  * **Then** the review is submitted with `event: APPROVE` and the GitHub API is called to promote the PR to Ready for Review

---

### Requirement Validation: REQ-023 (Stale Review Invalidation & Expiration)

#### Test Case: ATP-023-A (Stale review invalidation on new commit & 24h timeout)

**Description:** Pushing a new commit cancels outdated pending reviews; unapproved reviews expire after 24 hours.

* **User Scenario: SCN-023-A1**
  * **Given** a review pending approval for commit SHA-A
  * **When** a `synchronize` event arrives for commit SHA-B
  * **Then** the pending review for SHA-A is cancelled and a new review is queued for SHA-B
* **User Scenario: SCN-023-A2**
  * **Given** a review pending approval for > 24 hours
  * **When** the expiration sweeper runs
  * **Then** the pending review is marked expired and cleaned up

---

### Requirement Validation: REQ-024 (Dynamic Ngrok Webhook Auto-Registration)

#### Test Case: ATP-024-A (Ngrok URL discovery and webhook sync)

**Description:** Agent queries ngrok API on startup and updates registered webhook endpoints automatically.

* **User Scenario: SCN-024-A1**
  * **Given** ngrok tunnel is active at `http://localhost:4040/api/tunnels`
  * **When** the agent starts up or detects tunnel reconnect
  * **Then** the agent fetches the public HTTPS URL and registers/updates GitHub and Slack webhook subscriptions

---

### Requirement Validation: REQ-025 (2-Way Slack Integration Endpoint)

#### Test Case: ATP-025-A (Slack events, verification, and interactive commands)

**Description:** Agent processes Slack `url_verification`, `app_mention` commands, and interactive button clicks.

* **User Scenario: SCN-025-A1**
  * **Given** Slack sends a `url_verification` request to `/api/slack/events`
  * **When** the payload contains a challenge token
  * **Then** the system responds with JSON `{"challenge": "..."}` HTTP 200
* **User Scenario: SCN-025-A2**
  * **Given** a user posts `@PR-Reviewer review #1` in a Slack channel
  * **When** Slack sends an `app_mention` event to `/api/slack/events`
  * **Then** the agent parses the command and enqueues a PR review job

---

## Coverage Summary

| Metric | Count |
|--------|-------|
| Total Requirements (REQ) | 42 (42 active, 0 deprecated) |
| Total Test Cases (ATP) | 43 (43 active, 0 deprecated, 0 suspect) |
| Total Scenarios (SCN) | 74 |
| Active Requirements with ≥1 ATP | 42 / 42 (100%) |
| Test Cases with ≥1 SCN | 43 / 43 (100%) |
| **Overall Coverage** | **100%** (active items only) |

## Uncovered Requirements

None — full coverage achieved.

