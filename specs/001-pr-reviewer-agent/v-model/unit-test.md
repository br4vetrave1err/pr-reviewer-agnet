# Unit Test Plan: GitHub PR Review Agent

**Feature Branch**: `001-pr-reviewer-agent`
**Created**: 2026-08-01
**Status**: Approved
**Source**: `specs/001-pr-reviewer-agent/v-model/module-design.md`

## Overview

This document defines the Unit Test Plan for the GitHub PR Review Agent. Every module in `module-design.md` has at least one Test Case (UTP), and every Test Case has at least one executable Unit Scenario (UTS). Unit tests are white-box and verify a module's algorithm view, state machine, data structures, and error handling in isolation (collaborators stubbed).

## ID Schema

- **Unit Test Case**: `UTP-{NNN}-{X}` — where NNN matches the parent MOD, X is a letter suffix (A, B, C...)
- **Unit Test Scenario**: `UTS-{NNN}-{X}{#}` — nested under the parent UTP
- Example: `UTS-003-A1` → Scenario 1 of Test Case A verifying MOD-003

## White-Box Techniques

- **Statement Coverage** — every executable statement exercised
- **Branch Coverage** — both outcomes of every decision exercised
- **Boundary Value Analysis** — values at and around decision boundaries
- **Equivalence Partitioning** — representative inputs per partition
- **Error-Path Coverage** — every defined error path exercised

## Unit Tests

### MOD-001 (Webhook Handler)

**Parent**: ARCH-001, REQ-001

#### Test Case: UTP-001-A (Signature validation branches)

**Technique**: Branch Coverage
**Description**: Exercises both branches of the signature decision.

* **Unit Scenario: UTS-001-A1**
  * **Given** an event with a valid HMAC-SHA256 signature
  * **When** `parse_webhook(req)` runs
  * **Then** a typed event is returned and the guard passes
* **Unit Scenario: UTS-001-A2**
  * **Given** an event with a mismatched or missing signature
  * **When** `parse_webhook(req)` runs
  * **Then** a `SignatureError` is raised with no dispatch

---

### MOD-002 (Trigger Decision Engine)

**Parent**: ARCH-001, REQ-002

#### Test Case: UTP-002-A (Decision matrix boundaries)

**Technique**: Equivalence Partitioning
**Description**: Exercises author/reviewer/other and allow/deny partitions.

* **Unit Scenario: UTS-002-A1**
  * **Given** self as PR author, repo allowed
  * **When** `decide(event)` runs
  * **Then** the decision is `enqueue`
* **Unit Scenario: UTS-002-A2**
  * **Given** self as requested reviewer, repo allowed
  * **When** `decide(event)` runs
  * **Then** the decision is `enqueue`
* **Unit Scenario: UTS-002-A3**
  * **Given** self not author or reviewer
  * **When** `decide(event)` runs
  * **Then** the decision is `skip` with reason `not-self`
* **Unit Scenario: UTS-002-A4**
  * **Given** a denied repo
  * **When** `decide(event)` runs
  * **Then** the decision is `skip` with reason `not-allowed`

---

### MOD-003 (Command Parser)

**Parent**: ARCH-001, REQ-013

#### Test Case: UTP-003-A (Command syntax parsing)

**Technique**: Equivalence Partitioning
**Description**: Exercises valid commands, overrides, and malformed input.

* **Unit Scenario: UTS-003-A1**
  * **Given** body `@review --model gemini`
  * **When** `parse_command(body)` runs
  * **Then** `Command(review, model="gemini")` is returned
* **Unit Scenario: UTS-003-A2**
  * **Given** body with no command token
  * **When** `parse_command(body)` runs
  * **Then** `None` is returned
* **Unit Scenario: UTS-003-A3**
  * **Given** body with an unknown flag
  * **When** `parse_command(body)` runs
  * **Then** a `CommandSyntaxError` is raised

---

### MOD-004 (Queue Manager)

**Parent**: ARCH-002, REQ-004

#### Test Case: UTP-004-A (Enqueue boundaries)

**Technique**: Statement + Boundary Coverage
**Description**: Exercises duplicate, capacity, and lease paths.

* **Unit Scenario: UTS-004-A1**
  * **Given** a fresh dedup key
  * **When** `enqueue(job)` runs
  * **Then** a new run is created in `queued`
* **Unit Scenario: UTS-004-A2**
  * **Given** an existing dedup key
  * **When** `enqueue(job)` runs
  * **Then** a duplicate result is returned and no run is created
* **Unit Scenario: UTS-004-A3**
  * **Given** an expired worker lease
  * **When** `acquire_lease()` runs
  * **Then** the lease is re-acquirable and the row is recoverable

---

### MOD-005 (Worker Scheduler)

**Parent**: ARCH-002, REQ-004, REQ-NF-006

#### Test Case: UTP-005-A (Concurrency bound)

**Technique**: Statement Coverage
**Description**: Exercises the concurrency limit and backoff scheduling.

* **Unit Scenario: UTS-005-A1**
  * **Given** concurrency limit 2 and 10 queued jobs
  * **When** the scheduler dispatches
  * **Then** exactly 2 workers are active
* **Unit Scenario: UTS-005-A2**
  * **Given** a transient worker failure
  * **When** the scheduler requeues
  * **Then** backoff is applied and attempts increment up to the max

---

### MOD-006 (Clone Cache Manager)

**Parent**: ARCH-004, REQ-005

#### Test Case: UTP-006-A (Cache lifecycle boundaries)

**Technique**: Boundary Value Analysis
**Description**: Exercises create/update/evict against the disk cap.

* **Unit Scenario: UTS-006-A1**
  * **Given** no cached clone
  * **When** `ensure(owner, repo, head)` runs
  * **Then** a full clone is created
* **Unit Scenario: UTS-006-A2**
  * **Given** a cached clone with a newer head
  * **When** `ensure(owner, repo, head)` runs
  * **Then** a fetch updates the clone (no full re-clone)
* **Unit Scenario: UTS-006-A3**
  * **Given** cache above the disk cap
  * **When** `evict()` runs
  * **Then** LRU clones are removed until under the cap

---

### MOD-007 (Docs Loader)

**Parent**: ARCH-005, REQ-006

#### Test Case: UTP-007-A (Docs load and degradation)

**Technique**: Branch Coverage
**Description**: Exercises found and missing `specs/owner/repo/` folders.

* **Unit Scenario: UTS-007-A1**
  * **Given** a `specs/owner/repo/` folder in the docs tree
  * **When** `load(owner, repo)` runs
  * **Then** docs are returned with `degraded: false`
* **Unit Scenario: UTS-007-A2**
  * **Given** no folder for `owner/repo`
  * **When** `load(owner, repo)` runs
  * **Then** an empty docs set with `degraded: true` is returned

---

### MOD-008 (Workspace Runner)

**Parent**: ARCH-006, REQ-007

#### Test Case: UTP-008-A (Sandbox enforcement)

**Technique**: Statement Coverage
**Description**: Exercises the read-only guarantee and cleanup.

* **Unit Scenario: UTS-008-A1**
  * **Given** a run in progress
  * **When** the sandbox guard is checked
  * **Then** write/commit/push operations against the target repo are rejected
* **Unit Scenario: UTS-008-A2**
  * **Given** a finished run
  * **When** cleanup runs
  * **Then** the temp area is removed and the checkout is clean

---

### MOD-009 (CI Gate Monitor)

**Parent**: ARCH-006, REQ-010

#### Test Case: UTP-009-A (Gate resolution branches)

**Technique**: Branch Coverage
**Description**: Exercises settle-window bypass, failure detection, and wait-cap branches.

* **Unit Scenario: UTS-009-A1**
  * **Given** no CI runs configured for the head
  * **When** `resolve_gate(head)` runs after the settle window (75s)
  * **Then** the gate passes with reason `no-ci`
* **Unit Scenario: UTS-009-A2**
  * **Given** a gating CI run that completed with failure
  * **When** `resolve_gate(head)` runs
  * **Then** the gate fails and the failure details are returned for a diagnosis comment
* **Unit Scenario: UTS-009-A3**
  * **Given** a gating CI run still pending past the wait cap (60min)
  * **When** `resolve_gate(head)` runs
  * **Then** the gate times out and a single "CI hasn't completed; no review run" comment is queued

---

### MOD-010 (Test Compliance Validator)

**Parent**: ARCH-007, REQ-008

#### Test Case: UTP-010-A (Scope + compliance classification)

**Technique**: Equivalence Partitioning
**Description**: Exercises scope-violation and test-compliance partitions; never executes test suites.

* **Unit Scenario: UTS-010-A1**
  * **Given** a diff with files outside the PR's declared scope
  * **When** `validate_scope(diff, pr)` runs
  * **Then** a scope-violation finding is returned and the run continues
* **Unit Scenario: UTS-010-A2**
  * **Given** test additions that violate the repo's `AGENTS.md` / `.opencode/` rules
  * **When** `validate_compliance(tests, rules)` runs
  * **Then** a test-compliance finding is returned
* **Unit Scenario: UTS-010-A3**
  * **Given** a head whose gating CI ran green on GitHub
  * **When** compliance status is assembled
  * **Then** CI status is reported from GitHub and no local test execution occurs

---

### MOD-011 (Security Scan Runner)

**Parent**: ARCH-007, REQ-009

#### Test Case: UTP-011-A (Secrets scan scoping and skip branches)

**Technique**: Branch Coverage
**Description**: Exercises full-checkout gitleaks, green-head gating, and tool-missing branches.

* **Unit Scenario: UTS-011-A1**
  * **Given** a full-checkout secrets scan
  * **When** `run_secrets_scan()` runs
  * **Then** findings are normalized from the entire checkout
* **Unit Scenario: UTS-011-A2**
  * **Given** gating CI failed on the head
  * **When** the security scan phase is reached
  * **Then** the phase is skipped and logged (no scans on red heads)
* **Unit Scenario: UTS-011-A3**
  * **Given** a missing scanner binary
  * **When** the scan phase runs
  * **Then** the phase is skipped and logged without raising

---

### MOD-012 (LLM Security Reviewer)

**Parent**: ARCH-007, REQ-009

#### Test Case: UTP-012-A (LLM scan normalization)

**Technique**: Statement Coverage
**Description**: Exercises LLM scan invocation and normalization.

* **Unit Scenario: UTS-012-A1**
  * **Given** a code sample containing an injection sink
  * **When** `review_security()` runs
  * **Then** a finding with path, line, and severity is returned
* **Unit Scenario: UTS-012-A2**
  * **Given** an LLM provider timeout
  * **When** `review_security()` runs
  * **Then** the phase degrades gracefully with a logged error

---

### MOD-013 (GitHub Client)

**Parent**: ARCH-008, REQ-001, REQ-011

#### Test Case: UTP-013-A (API boundary error handling)

**Technique**: Error-Path Coverage
**Description**: Exercises the documented error paths.

* **Unit Scenario: UTS-013-A1**
  * **Given** a GitHub 404 for a PR
  * **When** the client fetches the PR
  * **Then** a `NotFoundError` is raised and mapped to `skipped`
* **Unit Scenario: UTS-013-A2**
  * **Given** a GitHub 403/429 response
  * **When** the client makes a call
  * **Then** a `RateLimitError` is raised carrying the Retry-After hint
* **Unit Scenario: UTS-013-A3**
  * **Given** a malformed payload with no PR
  * **When** the client parses it
  * **Then** a `MalformedDataError` is raised

---

### MOD-014 (Model Resolver)

**Parent**: ARCH-009, REQ-013

#### Test Case: UTP-014-A (Alias resolution)

**Technique**: Equivalence Partitioning
**Description**: Exercises known and unknown aliases plus defaults.

* **Unit Scenario: UTS-014-A1**
  * **Given** a configured alias
  * **When** `resolve(alias)` runs
  * **Then** a provider/model/auth-ref record is returned
* **Unit Scenario: UTS-014-A2**
  * **Given** an unknown alias
  * **When** `resolve(alias)` runs
  * **Then** an `UnknownAliasError` listing valid aliases is raised
* **Unit Scenario: UTS-014-A3**
  * **Given** no alias specified
  * **When** `resolve(None)` runs
  * **Then** the default alias from config is returned

#### Test Case: UTP-014-B (Active-model switching)

**Technique**: Branch Coverage
**Description**: Exercises the config-only model switch (REQ-016).

* **Unit Scenario: UTS-014-B1**
  * **Given** a defined provider alias and a changed `default_model`
  * **When** `switchDefault(alias)` then `resolve(None)` run
  * **Then** the new default alias is resolved without code changes
* **Unit Scenario: UTS-014-B2**
  * **Given** a `switchDefault` call with an undefined alias
  * **When** `switchDefault(alias)` runs
  * **Then** an `UnknownAliasError` is raised and the prior default is kept

---

### MOD-015 (State Repository)

**Parent**: ARCH-011, REQ-IF-005, REQ-NF-005

#### Test Case: UTP-015-A (Transactions and recovery)

**Technique**: Statement Coverage
**Description**: Exercises dedup, lease, and orphan recovery paths.

* **Unit Scenario: UTS-015-A1**
  * **Given** a dedup conflict on insert
  * **When** the insert runs
  * **Then** the conflict is caught and treated as duplicate
* **Unit Scenario: UTS-015-A2**
  * **Given** an expired lease row
  * **When** the recovery sweep runs
  * **Then** the row transitions to `queued` exactly once

---

### MOD-016 (Config Validator)

**Parent**: ARCH-012, REQ-IF-004, REQ-CN-001

#### Test Case: UTP-016-A (Validation branches)

**Technique**: Branch Coverage
**Description**: Exercises valid, invalid, and defaulted config.

* **Unit Scenario: UTS-016-A1**
  * **Given** a valid `config.yaml`
  * **When** `validate()` runs
  * **Then** a typed config with defaults applied is returned
* **Unit Scenario: UTS-016-A2**
  * **Given** a config with an invalid secret length
  * **When** `validate()` runs
  * **Then** a `ConfigError` is raised
* **Unit Scenario: UTS-016-A3**
  * **Given** a config missing required keys
  * **When** `validate()` runs
  * **Then** a `ConfigError` is raised

#### Test Case: UTP-016-B (Single-source model + agent skill set validation)

**Technique**: Branch Coverage
**Description**: Exercises REQ-016 single-app-layer model definition and the agent skill set config (REQ-017).

* **Unit Scenario: UTS-016-B1**
  * **Given** a config whose `default_model` is not among `providers`
  * **When** `validate()` runs
  * **Then** a `ConfigError` is raised (single source of truth violated)
* **Unit Scenario: UTS-016-B2**
  * **Given** a valid config with an `agent_skills` section
  * **When** `validate()` runs
  * **Then** the typed config exposes the base + situational skill names

---

### MOD-017 (Logger & Run Records)

**Parent**: ARCH-013, REQ-015

#### Test Case: UTP-017-A (Run record integrity)

**Technique**: Statement Coverage
**Description**: Exercises run record writes and redaction.

* **Unit Scenario: UTS-017-A1**
  * **Given** a completed run
  * **When** the record is written
  * **Then** the JSON record contains trigger, head SHA, model, phases, and outcome
* **Unit Scenario: UTS-017-A2**
  * **Given** a log line containing a secret value
  * **When** the logger emits it
  * **Then** the secret is redacted from the emitted output

---

### MOD-018 (Rate Limiter)

**Parent**: ARCH-013, REQ-NF-004

#### Test Case: UTP-018-A (Backoff boundary)

**Technique**: Boundary Value Analysis
**Description**: Exercises the backoff schedule at attempt boundaries.

* **Unit Scenario: UTS-018-A1**
  * **Given** a rate-limit error on attempt 1
  * **When** `backoff_delay(attempt)` runs
  * **Then** the delay is within `[base, base*jitter]`
* **Unit Scenario: UTS-018-A2**
  * **Given** attempts at the max retry boundary
  * **When** `backoff_delay(attempt)` runs
  * **Then** the delay saturates at the configured maximum

---

### MOD-019 (Skill Set Selector)

**Parent**: ARCH-006, REQ-017

#### Test Case: UTP-019-A (Defined agent skill set selection)

**Technique**: Branch Coverage
**Description**: Exercises the base skill, situational skill triggers, and repo/vendored merge.

* **Unit Scenario: UTS-019-A1**
  * **Given** no bug or merge-conflict findings
  * **When** `select(findings, repoSkills, vendoredSkills)` runs
  * **Then** `/code-review` is always present as the base skill
* **Unit Scenario: UTS-019-A2**
  * **Given** a bug-type finding
  * **When** `select(findings, ...)` runs
  * **Then** `/diagnosing-bugs` is included in the skill set
* **Unit Scenario: UTS-019-A3**
  * **Given** a merge-conflict-type finding
  * **When** `select(findings, ...)` runs
  * **Then** `/resolving-merge-conflicts` is included in the skill set
* **Unit Scenario: UTS-019-A4**
  * **Given** repo skills and the vendored `.agents/skills/` set present
  * **When** `select(findings, repoSkills, vendoredSkills)` runs
  * **Then** they are merged and deduplicated with the base skill set

---

## Coverage Summary

| Metric | Count |
|--------|-------|
| Total Modules (MOD) | 19 (19 active, 0 deprecated) |
| Total Test Cases (UTP) | 21 |
| Total Scenarios (UTS) | 55 |
| Modules with ≥1 UTP | 19 / 19 (100%) (active items only) |
| Test Cases with ≥1 UTS | 21 / 21 (100%) |
| **Overall Coverage (MOD→UTP)** | **100%** |

## Uncovered Modules

None — full coverage achieved.
