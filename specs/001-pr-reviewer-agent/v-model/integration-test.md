# Integration Test Plan: GitHub PR Review Agent

**Feature Branch**: `001-pr-reviewer-agent`
**Created**: 2026-08-01
**Status**: Approved
**Source**: `specs/001-pr-reviewer-agent/v-model/architecture-design.md`

## Overview

This document defines the Integration Test Plan for the GitHub PR Review Agent. Every architectural element in `architecture-design.md` has at least one Test Case (ITP), and every Test Case has at least one executable Integration Scenario (ITS) in technical BDD format. Integration tests verify that modules collaborate as the architecture specifies.

## ID Schema

- **Integration Test Case**: `ITP-{NNN}-{X}` — where NNN matches the parent ARCH, X is a letter suffix (A, B, C...)
- **Integration Test Scenario**: `ITS-{NNN}-{X}{#}` — nested under the parent ITP
- Example: `ITS-002-A1` → Scenario 1 of Test Case A verifying ARCH-002

## ISO 29119-4 Integration Techniques

- **Big-Bang** — All modules integrated and exercised together end-to-end
- **Top-Down** — Start from entry points, stub downstream collaborators
- **Bottom-Up** — Start from leaf modules, integrate upward

## Integration Tests

### ARCH-001 (Webhook Server)

**Parent Requirements**: REQ-001, REQ-IF-002, REQ-NF-002

#### Test Case: ITP-001-A (Receiver wired to config secret and trigger filter)

**Technique**: Top-Down
**Description**: Validates the receiver hands validated events to the trigger filter using the configured secret, and ACKs fast.

* **Integration Scenario: ITS-001-A1**
  * **Given** a running service with a config-provided webhook secret and a subscribed (author) event
  * **When** a signed delivery is POSTed to `/api/webhook`
  * **Then** the receiver validates against the config secret, the trigger filter yields `enqueue`, and an ACK is returned within 2 seconds
* **Integration Scenario: ITS-001-A2**
  * **Given** a running service with an unsigned delivery
  * **When** a delivery is POSTed to `/api/webhook`
  * **Then** the receiver returns 401 and the trigger filter is never invoked

---

### ARCH-002 (Trigger & Command Filter)

**Parent Requirements**: REQ-002, REQ-003, REQ-013

#### Test Case: ITP-002-A (Trigger decision and comment command wired to queue)

**Technique**: Bottom-Up
**Description**: Validates that trigger decisions and parsed commands both produce durable queue entries.

* **Integration Scenario: ITS-002-A1**
  * **Given** an accepted author/reviewer trigger on an allowed repo
  * **When** the filter emits its decision
  * **Then** an `enqueue` job with the PR head is produced
* **Integration Scenario: ITS-002-A2**
  * **Given** a denied repo or a malformed `@review` command
  * **When** the filter evaluates
  * **Then** no job is enqueued and either a skip reason or help reply is emitted

---

### ARCH-003 (Queue & Scheduler)

**Parent Requirements**: REQ-004, REQ-012, REQ-014, REQ-NF-005, REQ-NF-006

#### Test Case: ITP-003-A (Enqueue persists before ack; full pipeline completes)

**Technique**: Big-Bang
**Description**: Validates durability-before-ack and the full review pipeline against a real test PR.

* **Integration Scenario: ITS-003-A1**
  * **Given** an accepted trigger decision
  * **When** the enqueue path runs
  * **Then** a durable row exists in the store before the HTTP response is sent, and the worker observes it
* **Integration Scenario: ITS-003-A2**
  * **Given** a test PR on a throwaway GitHub repo
  * **When** the orchestrator runs clone → docs → tests → security → review → publish
  * **Then** a review is posted with a summary, verdict, and inline comments

#### Test Case: ITP-003-B (Dedup, re-review, and retry behavior)

**Technique**: Bottom-Up
**Description**: Validates dedup on same head and re-review on new head.

* **Integration Scenario: ITS-003-B1**
  * **Given** two identical accepted decisions for the same head
  * **When** both enqueue paths run
  * **Then** exactly one run row is created (dedup honored by the store)
* **Integration Scenario: ITS-003-B2**
  * **Given** a test PR whose head SHA changes while a run is pending
  * **When** the new push arrives
  * **Then** a new run for the new SHA is enqueued and the earlier one resolves without double-post

---

### ARCH-004 (Repo Clone Cache)

**Parent Requirements**: REQ-005

#### Test Case: ITP-004-A (Ensure cache wired to git and workers)

**Technique**: Bottom-Up
**Description**: Validates that workers use the cache manager so clones are shared, not duplicated.

* **Integration Scenario: ITS-004-A1**
  * **Given** two consecutive runs on the same repo
  * **When** both runs call `ensure(owner, repo, head)`
  * **Then** the second run reuses the cached clone and the git metadata is up to date
* **Integration Scenario: ITS-004-A2**
  * **Given** a cache at the disk cap
  * **When** a new repo requires a clone
  * **Then** eviction frees space and the new clone succeeds

---

### ARCH-005 (Docs Provider)

**Parent Requirements**: REQ-006, REQ-IF-006

#### Test Case: ITP-005-A (Docs loader wired to the review prompt)

**Technique**: Top-Down
**Description**: Validates docs are delivered to the executor and degraded runs proceed.

* **Integration Scenario: ITS-005-A1**
  * **Given** a `specs/owner/repo/` folder in this repo's docs tree and a run for that repo
  * **When** the orchestrator assembles the prompt
  * **Then** the docs are present in the prompt context
* **Integration Scenario: ITS-005-A2**
  * **Given** the `specs/` tree is absent or unreadable
  * **When** the orchestrator assembles the prompt
  * **Then** the run proceeds with an empty docs context and a warning is recorded

---

### ARCH-006 (Workspace Runner)

**Parent Requirements**: REQ-007, REQ-010, REQ-017, REQ-IF-003, REQ-CN-003

#### Test Case: ITP-006-A (Executor sandbox and cleanup)

**Technique**: Bottom-Up
**Description**: Validates the executor's isolation, skills availability, and cleanup contract.

* **Integration Scenario: ITS-006-A1**
  * **Given** a workspace with repo skills and the vendored `.agents/skills/` directory in the image
  * **When** the executor spawns `opencode run` as a one-off CLI subprocess with a resolved model
  * **Then** output JSON is parsed, and no target-repo write escapes the sandbox
* **Integration Scenario: ITS-006-A2**
  * **Given** a head whose gating CI failed
  * **When** the executor finishes
  * **Then** a diagnosis comment is queued and no review is produced (REQ-010)
* **Integration Scenario: ITS-006-A3**
  * **Given** a workspace with the agent's defined skill set configured
  * **When** the executor assembles the opencode invocation for a run with a bug finding
  * **Then** `/code-review` and `/diagnosing-bugs` are injected alongside the repo's own skills, and `/resolving-merge-conflicts` when a merge conflict is spotted (REQ-017)

---

### ARCH-007 (Scope & Test Compliance Validator)

**Parent Requirements**: REQ-008

#### Test Case: ITP-007-A (Scope + compliance phases produce normalized findings)

**Technique**: Bottom-Up
**Description**: Validates scope-boundary and test-compliance results normalize into the shared findings structure; test suites are never executed locally.

* **Integration Scenario: ITS-007-A1**
  * **Given** a PR whose diff contains files outside the declared scope
  * **When** the orchestrator runs the scope validation phase
  * **Then** a scope-violation finding appears in the findings list and the run continues
* **Integration Scenario: ITS-007-A2**
  * **Given** test additions that violate the repo's `AGENTS.md` / `.opencode/` rules
  * **When** the orchestrator runs the compliance validation phase
  * **Then** a test-compliance finding is recorded, CI status is taken from GitHub, and no local test execution occurs

---

### ARCH-008 (Security Scan Pipeline)

**Parent Requirements**: REQ-009

#### Test Case: ITP-008-A (Security phases normalize findings)

**Technique**: Bottom-Up
**Description**: Validates gitleaks and the in-session LLM security review feed a single normalized findings list.

* **Integration Scenario: ITS-008-A1**
  * **Given** a checkout with a hard-coded secret
  * **When** the security pipeline runs on a green head
  * **Then** the gitleaks secret finding appears in the shared findings list
* **Integration Scenario: ITS-008-A2**
  * **Given** changed files with a security-relevant pattern
  * **When** the LLM security review runs inside the review session
  * **Then** a security finding appears in the shared findings list; a missing gitleaks binary only skips that phase without failing the run

---

### ARCH-009 (GitHub API Client)

**Parent Requirements**: REQ-011, REQ-012, REQ-IF-001

#### Test Case: ITP-009-A (REST operations wired to the pipeline)

**Technique**: Top-Down
**Description**: Validates PR reads, comment creation, and review submission are correctly wired, including error mapping.

* **Integration Scenario: ITS-009-A1**
  * **Given** an assembled review payload with summary, verdict, and inline comments
  * **When** the payload is submitted to the GitHub Reviews API
  * **Then** the API accepts it (201) and the review appears on the PR
* **Integration Scenario: ITS-009-A2**
  * **Given** a GitHub 404 for the PR
  * **When** the client fetches the PR
  * **Then** the run is marked `skipped` and no review is posted

---

### ARCH-010 (Model Registry)

**Parent Requirements**: REQ-013, REQ-016

#### Test Case: ITP-010-A (Model resolution wired to run records)

**Technique**: Top-Down
**Description**: Validates that resolved models are recorded and failed resolutions fail the run.

* **Integration Scenario: ITS-010-A1**
  * **Given** a PR command `@review --model go`
  * **When** the orchestrator resolves and runs
  * **Then** the run record contains the resolved provider/model and the review succeeds
* **Integration Scenario: ITS-010-A2**
  * **Given** a PR command `@review --model nope`
  * **When** the orchestrator attempts resolution
  * **Then** the run fails before execution with an UnknownAlias error logged
* **Integration Scenario: ITS-010-A3**
  * **Given** a config-only `default_model` change to an existing alias
  * **When** a run without an override resolves the model
  * **Then** the new default is used without any code change (REQ-016)

---

### ARCH-011 (State Store)

**Parent Requirements**: REQ-IF-005, REQ-NF-005

#### Test Case: ITP-011-A (State store recovers orphans on boot)

**Technique**: Bottom-Up
**Description**: Validates crash recovery against the architecture's state model.

* **Integration Scenario: ITS-011-A1**
  * **Given** orphaned `running` rows after a simulated crash
  * **When** the service boots
  * **Then** the orphans are requeued and no double-post occurs
* **Integration Scenario: ITS-011-A2**
  * **Given** an in-flight run holding a lease
  * **When** the lease expires
  * **Then** the row is recoverable and the run is eventually processed once

---

### ARCH-012 (Config Loader)

**Parent Requirements**: REQ-IF-004, REQ-016, REQ-017, REQ-CN-001

#### Test Case: ITP-012-A (Config failure halts boot)

**Technique**: Top-Down
**Description**: Validates fail-closed startup wiring.

* **Integration Scenario: ITS-012-A1**
  * **Given** an invalid `config.yaml`
  * **When** the service boots
  * **Then** boot aborts with a ConfigError and no webhook or queue starts
* **Integration Scenario: ITS-012-A2**
  * **Given** a `config.yaml` whose `default_model` is not a defined provider alias, or with an invalid `agent_skills` section
  * **When** the service boots
  * **Then** boot aborts with a ConfigError before any run is accepted (REQ-016, REQ-017)

---

### ARCH-013 (Observability & Runtime)

**Parent Requirements**: REQ-015, REQ-NF-001, REQ-NF-002, REQ-NF-003, REQ-NF-004

#### Test Case: ITP-013-A (Runtime signals and secret hygiene end-to-end)

**Technique**: Big-Bang
**Description**: Validates shutdown, rate-limit backoff, and no secret leakage across the full process.

* **Integration Scenario: ITS-013-A1**
  * **Given** a running service with queued work
  * **When** SIGTERM is sent
  * **Then** the service drains, closes the DB, and exits 0
* **Integration Scenario: ITS-013-A2**
  * **Given** a GitHub rate-limit (403/429) during a run
  * **When** the pipeline calls GitHub again
  * **Then** jittered exponential backoff is applied and the run eventually completes or reports partial
* **Integration Scenario: ITS-013-A3**
  * **Given** a full completed run
  * **When** the run record, logs, and posted review are scanned
  * **Then** no secret value (PAT, webhook secret, provider keys) is present anywhere

---

## Coverage Summary

| Metric | Count |
|--------|-------|
| Total Architectural Elements (ARCH) | 13 (13 active, 0 deprecated) |
| Total Test Cases (ITP) | 14 |
| Total Scenarios (ITS) | 31 |
| Elements with ≥1 ITP | 13 / 13 (100%) (active items only) |
| Test Cases with ≥1 ITS | 14 / 14 (100%) |
| **Overall Coverage (ARCH→ITP)** | **100%** |

## Uncovered Elements

None — full coverage achieved.
