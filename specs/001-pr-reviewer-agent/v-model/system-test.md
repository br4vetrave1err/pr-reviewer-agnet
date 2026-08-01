# System Test Plan: GitHub PR Review Agent

**Feature Branch**: `001-pr-reviewer-agent`
**Created**: 2026-08-01
**Status**: Approved
**Source**: `specs/001-pr-reviewer-agent/v-model/system-design.md`

## Overview

This document defines the System Test Plan for the GitHub PR Review Agent. Every system component in `system-design.md` has at least one Test Case (STP), and every Test Case has at least one executable System Scenario (STS) in technical BDD format. System tests verify architectural behavior, not user journeys.

## ID Schema

- **System Test Case**: `STP-{NNN}-{X}` — where NNN matches the parent SYS, X is a letter suffix (A, B, C...)
- **System Test Scenario**: `STS-{NNN}-{X}{#}` — nested under the parent STP, with numeric suffix (1, 2, 3...)
- Example: `STS-001-A1` → Scenario 1 of Test Case A verifying SYS-001

## ISO 29119 Test Techniques

- **Interface Contract Testing** — Verifies API contracts from the Interface View
- **Boundary Value Analysis** — Tests data limits from the Data Design View
- **Equivalence Partitioning** — Tests representative data classes
- **Fault Injection** — Tests failure propagation from the Dependency View

## System Tests

### Component Verification: SYS-001 (Webhook Receiver)

**Parent Requirements**: REQ-001, REQ-IF-002, REQ-NF-002

#### Test Case: STP-001-A (Signature gate and fast ACK)

**Technique**: Interface Contract Testing
**Target View**: Interface View
**Description**: Verifies the webhook contract: valid signatures processed, invalid rejected with 401, ACK under 2s.

* **System Scenario: STS-001-A1**
  * **Given** an HTTP POST to `/api/webhook` with a valid `X-Hub-Signature-256`
  * **When** the receiver validates the HMAC and dispatches the event
  * **Then** HTTP 200 is returned within 2 seconds and the normalized event is handed to SYS-002
* **System Scenario: STS-001-A2**
  * **Given** an HTTP POST to `/api/webhook` with an invalid signature
  * **When** the receiver validates the HMAC
  * **Then** HTTP 401 is returned and no event is dispatched

#### Test Case: STP-001-B (Receiver survives dispatcher backpressure)

**Technique**: Fault Injection
**Target View**: Dependency View
**Description**: The receiver does not block on the downstream pipeline.

* **System Scenario: STS-001-B1**
  * **Given** the queue and worker pool are saturated
  * **When** a new valid delivery arrives
  * **Then** the receiver still ACKs within 2 seconds and the event is queued

---

### Component Verification: SYS-002 (Trigger Filter)

**Parent Requirements**: REQ-002, REQ-003

#### Test Case: STP-002-A (Trigger + managed-repo decision matrix)

**Technique**: Equivalence Partitioning
**Target View**: Interface View
**Description**: Verifies the decision partitioning over (author/reviewer/other) × (in `repo_config`/denied).

* **System Scenario: STS-002-A1**
  * **Given** an event where the self-account is the PR author and the repo is in `repo_config`
  * **When** the filter evaluates the event
  * **Then** the decision is `enqueue` with the PR head
* **System Scenario: STS-002-A2**
  * **Given** an event where the self-account is not author or reviewer
  * **When** the filter evaluates the event
  * **Then** the decision is `skip` with reason `not-self`
* **System Scenario: STS-002-A3**
  * **Given** an event for a repo not in `repo_config`, or listed in the denylist
  * **When** the filter evaluates the event
  * **Then** the decision is `skip` with reason `not-managed`

---

### Component Verification: SYS-003 (Review Coordinator)

**Parent Requirements**: REQ-004, REQ-012, REQ-014, REQ-NF-005, REQ-NF-006

#### Test Case: STP-003-A (Dedup, concurrency bound, and retry)

**Technique**: Interface Contract Testing
**Target View**: Process View
**Description**: Verifies the coordinator's queue behavior: dedup, bounded concurrency, backoff retry.

* **System Scenario: STS-003-A1**
  * **Given** a dedup insert for (owner, repo, pr, head, model) already exists
  * **When** the coordinator attempts to enqueue the same key
  * **Then** the enqueue coalesces to a duplicate result and no new run is created
* **System Scenario: STS-003-A2**
  * **Given** concurrency configured to 1 and 10 queued runs
  * **When** the coordinator schedules workers
  * **Then** exactly 1 run executes at a time and the rest remain queued
* **System Scenario: STS-003-A3**
  * **Given** a transient failure in a running run with attempts below the max
  * **When** the worker reports the failure
  * **Then** the run is requeued with backoff and an incremented attempt count

#### Test Case: STP-003-B (Always-COMMENT verdict)

**Technique**: Equivalence Partitioning
**Target View**: Interface View
**Description**: Verifies reviews are always posted with event `COMMENT`; the verdict is prose in the summary.

* **System Scenario: STS-003-B1**
  * **Given** a repo with blocking-severity findings
  * **When** the coordinator resolves the verdict
  * **Then** the summary states an advisory verdict in prose ("changes needed") and the event is `COMMENT` (never `REQUEST_CHANGES`)
* **System Scenario: STS-003-B2**
  * **Given** a clean pass
  * **When** the coordinator resolves the verdict
  * **Then** the event is `COMMENT` (never `APPROVE`) and the summary notes the clean pass

---

### Component Verification: SYS-004 (Repo Clone Cache)

**Parent Requirements**: REQ-005

#### Test Case: STP-004-A (Clone/update/evict lifecycle)

**Technique**: Boundary Value Analysis
**Target View**: Data Design View
**Description**: Verifies cache lifecycle behavior at the disk-cap boundary.

* **System Scenario: STS-004-A1**
  * **Given** no cached clone for a repo
  * **When** `ensure(owner, repo, head)` is called
  * **Then** a full clone is created at the resolved cache path
* **System Scenario: STS-004-A2**
  * **Given** a cached clone and a newer head
  * **When** `ensure(owner, repo, head)` is called
  * **Then** the clone is updated via fetch, not re-cloned
* **System Scenario: STS-004-A3**
  * **Given** total cache size above the disk cap
  * **When** `ensure` requires a new clone
  * **Then** least-recently-used clones are evicted until under the cap

---

### Component Verification: SYS-005 (Docs Context Loader)

**Parent Requirements**: REQ-006, REQ-IF-006

#### Test Case: STP-005-A (Docs load and graceful degradation)

**Technique**: Interface Contract Testing
**Target View**: Interface View
**Description**: Verifies docs loading contract and degradation.

* **System Scenario: STS-005-A1**
  * **Given** a `specs/owner/repo/` folder in this repo's docs tree
  * **When** `load(owner, repo)` is called
  * **Then** the markdown files under the folder are returned with `degraded: false`
* **System Scenario: STS-005-A2**
  * **Given** no `specs/owner/repo/` folder in this repo's docs tree
  * **When** `load(owner, repo)` is called
  * **Then** an empty docs set with `degraded: true` is returned

#### Test Case: STP-005-B (Docs tree absent or unreadable)

**Technique**: Fault Injection
**Target View**: Dependency View
**Description**: Verifies isolation when the docs dependency fails.

* **System Scenario: STS-005-B1**
  * **Given** the `specs/` tree is absent or unreadable
  * **When** `load(owner, repo)` is called
  * **Then** a warning is recorded and the run proceeds with no docs

---

### Component Verification: SYS-006 (Review Executor)

**Parent Requirements**: REQ-007, REQ-010, REQ-017, REQ-IF-003, REQ-CN-003

#### Test Case: STP-006-A (Headless opencode execution contract)

**Technique**: Interface Contract Testing
**Target View**: Interface View
**Description**: Verifies the one-off `opencode run` CLI subprocess contract, vendored skills availability, and read-only enforcement.

* **System Scenario: STS-006-A1**
  * **Given** a checkout with repo skills and the vendored `.agents/skills/` directory in the image
  * **When** the executor spawns `opencode run` as a one-off subprocess with a resolved model
  * **Then** the process exits 0 and a parseable result JSON is returned
* **System Scenario: STS-006-A2**
  * **Given** a run in progress
  * **When** the executor enforces read-only on the clone
  * **Then** no commit, branch, or push operation is permitted against the target repo
* **System Scenario: STS-006-A3**
  * **Given** an executor run with a bug finding and a merge conflict spotted
  * **When** the defined agent skill set is assembled
  * **Then** `/code-review`, `/diagnosing-bugs`, and `/resolving-merge-conflicts` are available to the agent alongside the repo's own skills (REQ-017)

#### Test Case: STP-006-B (CI gate outcome: diagnosis, not review)

**Technique**: Equivalence Partitioning
**Target View**: Process View
**Description**: Verifies the executor only reviews green heads; a gating failure yields a root-cause diagnosis comment instead of a review.

* **System Scenario: STS-006-B1**
  * **Given** the head's gating CI completed with a failure
  * **When** the executor's gate resolves
  * **Then** no review is produced and a diagnosis comment with the root cause (fetched CI logs) is queued
* **System Scenario: STS-006-B2**
  * **Given** a head with no configured CI
  * **When** the settle window (75s) elapses
  * **Then** the run proceeds to review (no-CI bypass)

---

### Component Verification: SYS-007 (PR Scope & Test Compliance Validator)

**Parent Requirements**: REQ-008

#### Test Case: STP-007-A (Scope + compliance validation, no test execution)

**Technique**: Equivalence Partitioning
**Target View**: Interface View
**Description**: Verifies scope boundary and test-compliance findings (discovery only); the container never executes the repo's test suites.

* **System Scenario: STS-007-A1**
  * **Given** changed files that do not pertain to the PR details / linked issues
  * **When** the validator runs
  * **Then** a scope-violation finding is listed and the run continues (non-blocking)
* **System Scenario: STS-007-A2**
  * **Given** test additions that violate the repo's `AGENTS.md` / `.opencode/` rules
  * **When** the validator runs
  * **Then** a test-compliance finding is produced
* **System Scenario: STS-007-A3**
  * **Given** a head whose gating CI ran green on GitHub
  * **When** the validator runs
  * **Then** CI status is taken from GitHub and no local test execution occurs

---

### Component Verification: SYS-008 (Security Scanner)

**Parent Requirements**: REQ-009

#### Test Case: STP-008-A (Scan scoping and normalization)

**Technique**: Interface Contract Testing
**Target View**: Interface View
**Description**: Verifies gitleaks (full checkout) and the in-session LLM security review, plus tool-missing degradation.

* **System Scenario: STS-008-A1**
  * **Given** a checkout containing a hard-coded secret
  * **When** the gitleaks scan (full checkout) runs
  * **Then** a normalized secret finding is produced
* **System Scenario: STS-008-A2**
  * **Given** changed files with a security-relevant change pattern
  * **When** the LLM security review runs inside the review session
  * **Then** a security finding is produced for those changed files
* **System Scenario: STS-008-A3**
  * **Given** a scanner tool missing from the image
  * **When** the pipeline reaches that phase
  * **Then** the phase is skipped, logged, and the run continues

---

### Component Verification: SYS-009 (Report Publisher)

**Parent Requirements**: REQ-011, REQ-012, REQ-IF-001

#### Test Case: STP-009-A (Review submission and state update)

**Technique**: Interface Contract Testing
**Target View**: Interface View
**Description**: Verifies the review is posted with summary + inline comments and state is updated.

* **System Scenario: STS-009-A1**
  * **Given** an assembled review payload with summary, verdict, and inline comments
  * **When** the publisher submits via the GitHub REST API
  * **Then** the review is created and the run status becomes `posted`
* **System Scenario: STS-009-A2**
  * **Given** a GitHub 404 for the PR
  * **When** the publisher submits the review
  * **Then** the run is marked `skipped` and no review is posted

---

### Component Verification: SYS-010 (Model Registry)

**Parent Requirements**: REQ-013, REQ-016

#### Test Case: STP-010-A (Alias resolution)

**Technique**: Equivalence Partitioning
**Target View**: Interface View
**Description**: Verifies alias resolution including unknown aliases.

* **System Scenario: STS-010-A1**
  * **Given** a configured alias `go`
  * **When** `resolve("go")` is called
  * **Then** a provider/model/auth-ref record is returned
* **System Scenario: STS-010-A2**
  * **Given** an alias not in config (e.g. `gemini`, disabled)
  * **When** `resolve("nope")` is called
  * **Then** an UnknownAlias error is raised listing valid aliases
* **System Scenario: STS-010-A3**
  * **Given** a config-only change of `default_model` to an existing alias (e.g. when a provider's credits are exhausted)
  * **When** a review runs without an override
  * **Then** the new default is used, and per-PR `@review --model <alias>` overrides still take precedence (REQ-016)

---

### Component Verification: SYS-011 (Comment Command Interpreter)

**Parent Requirements**: REQ-013

#### Test Case: STP-011-A (Comment command parsing)

**Technique**: Interface Contract Testing
**Target View**: Interface View
**Description**: Verifies command parsing and help replies.

* **System Scenario: STS-011-A1**
  * **Given** an issue_comment body `@review --model go`
  * **When** the interpreter parses the body
  * **Then** a `review` command with model `go` is produced
* **System Scenario: STS-011-A2**
  * **Given** an issue_comment body with malformed syntax
  * **When** the interpreter parses the body
  * **Then** a help reply is posted and no run is enqueued

---

### Component Verification: SYS-012 (State Store)

**Parent Requirements**: REQ-IF-005, REQ-NF-005

#### Test Case: STP-012-A (Transactional dedup and recovery)

**Technique**: Fault Injection
**Target View**: Data Design View
**Description**: Verifies the SQLite dedup unique constraint and orphan recovery.

* **System Scenario: STS-012-A1**
  * **Given** an existing row for (owner, repo, pr, head, model)
  * **When** a dedup insert for the same key executes
  * **Then** the insert is ignored (0 rows affected) and treated as a duplicate
* **System Scenario: STS-012-A2**
  * **Given** rows in `running` state older than the lease TTL after a crash
  * **When** the boot recovery sweep runs
  * **Then** those rows are requeued as `queued` and no double-post occurs

---

### Component Verification: SYS-013 (Config Manager)

**Parent Requirements**: REQ-IF-004, REQ-016, REQ-CN-001

#### Test Case: STP-013-A (Config load and fail-closed validation)

**Technique**: Interface Contract Testing
**Target View**: Interface View
**Description**: Verifies config validation behavior.

* **System Scenario: STS-013-A1**
  * **Given** a valid `config.yaml`
  * **When** the config manager loads it
  * **Then** a typed config with defaults applied is returned
* **System Scenario: STS-013-A2**
  * **Given** an invalid `config.yaml`
  * **When** the config manager loads it
  * **Then** a ConfigError is raised and the service refuses to boot
* **System Scenario: STS-013-A3**
  * **Given** a `config.yaml` that defines `providers`/`default_model` once and an `agent_skills` section
  * **When** the config manager loads it
  * **Then** the single model definition is validated (default in providers) and the skill set is typed; a violating config fails closed (REQ-016, REQ-017)

---

### Component Verification: SYS-014 (Runtime & Observability)

**Parent Requirements**: REQ-015, REQ-NF-001, REQ-NF-003, REQ-NF-004, REQ-NF-007, REQ-CN-002, REQ-CN-004

#### Test Case: STP-014-A (Run records, rate-limit policy, secret hygiene)

**Technique**: Interface Contract Testing
**Target View**: Data Design View
**Description**: Verifies run records, backoff policy, and that no secrets leak.

* **System Scenario: STS-014-A1**
  * **Given** a completed run
  * **When** the run record is written
  * **Then** a JSON run record with trigger, head SHA, model, phases, and outcome is persisted under `.runs/`
* **System Scenario: STS-014-A2**
  * **Given** a GitHub 403/429 response
  * **When** the rate-limit policy is applied
  * **Then** a jittered exponential backoff is scheduled
* **System Scenario: STS-014-A3**
  * **Given** a completed run whose logs and artifacts are inspected
  * **When** the secret scan on the agent's own output runs
  * **Then** no secret value (PAT, webhook secret, provider keys) is present

#### Test Case: STP-014-B (Graceful shutdown)

**Technique**: Fault Injection
**Target View**: Process View
**Description**: Verifies drain-and-exit on shutdown.

* **System Scenario: STS-014-B1**
  * **Given** a SIGTERM while jobs are queued and running
  * **When** the runtime handles the signal
  * **Then** the queue drains, the DB closes cleanly, and the process exits 0

---

## Coverage Summary

| Metric | Count |
|--------|-------|
| Total System Components (SYS) | 14 (14 active, 0 deprecated) |
| Total Test Cases (STP) | 19 |
| Total Scenarios (STS) | 44 |
| Components with ≥1 STP | 14 / 14 (100%) (active items only) |
| Test Cases with ≥1 STS | 19 / 19 (100%) |
| **Overall Coverage (SYS→STP)** | **100%** |

## Uncovered Components

None — full coverage achieved.
