# Hazard Analysis (FMEA): GitHub PR Review Agent

**Feature Branch**: `001-pr-reviewer-agent`
**Created**: 2026-08-01
**Status**: Approved
**Source**: `specs/001-pr-reviewer-agent/v-model/system-design.md`
**Standard**: General-Purpose FMEA (domain overlay may apply)

## Overview

This document presents the Failure Mode and Effects Analysis (FMEA) for the GitHub PR Review Agent.
Every system component (`SYS-NNN`) from `system-design.md` is assessed for potential failure
modes across the operational states defined in the system design. Each hazard receives a
unique `HAZ-NNN` identifier and is linked to risk control measures (`REQ-NNN` / `SYS-NNN`),
enabling the traceability chain: Hazard → Mitigation → Requirement → Test Case (Matrix H).

## ID Schema

- **Hazard ID**: `HAZ-{NNN}` — 3-digit zero-padded, sequential (HAZ-001, HAZ-002, ...)
- **ID Lineage**: From `HAZ-001`, read the Mitigation column to find `REQ-NNN` / `SYS-NNN`.
  Consult `traceability-matrix.md` (Matrix H) for the full chain to verification test cases.

## Risk Matrix Definition

### Severity Scale

| Level | Definition |
|-------|-----------|
| Catastrophic | Death or permanent injury; complete system destruction |
| Critical | Severe injury or major system damage; immediate intervention required |
| Serious | Moderate injury or significant degradation; medical attention needed |
| Minor | Slight injury or minor degradation; first aid sufficient |
| Negligible | No injury; cosmetic or inconvenience-level impact |

### Likelihood Scale

| Level | Definition |
|-------|-----------|
| Frequent | Likely to occur often; continuously experienced |
| Probable | Will occur several times; expected to occur |
| Occasional | Likely to occur sometime; can reasonably be expected |
| Remote | Unlikely but possible; could occur in the life of the system |
| Improbable | So unlikely it can be assumed it will not occur |

### Risk Matrix (Severity × Likelihood)

| | Frequent | Probable | Occasional | Remote | Improbable |
|---|---|---|---|---|---|
| **Catastrophic** | Unacceptable | Unacceptable | Unacceptable | Undesirable | Undesirable |
| **Critical** | Unacceptable | Unacceptable | Undesirable | Undesirable | Tolerable |
| **Serious** | Unacceptable | Undesirable | Undesirable | Tolerable | Tolerable |
| **Minor** | Undesirable | Tolerable | Tolerable | Acceptable | Acceptable |
| **Negligible** | Tolerable | Acceptable | Acceptable | Acceptable | Acceptable |

## Operational States Reference

| State | Description | Source |
|-------|------------|--------|
| NORMAL | Implicit default state (no operational states defined in system-design.md) | Implicit |

⚠️ No operational states defined in system-design.md — using implicit NORMAL state.

## Hazard Register (FMEA)

| HAZ ID | Component | Failure Mode | Operational State | Effect | Severity | Likelihood | Risk Level | Mitigation | Residual Risk |
|--------|-----------|-------------|-------------------|--------|----------|-----------|------------|------------|---------------|
| HAZ-001 | SYS-001 | Webhook HMAC signature verification bypassed or weakened | NORMAL | Forged webhook event triggers an unwanted review or leaks PR information | Critical | Remote | Undesirable | REQ-001, REQ-IF-002 | Tolerable with mandatory `X-Hub-Signature-256` verification |
| HAZ-002 | SYS-001 | Webhook ACK exceeds the 2s budget (synchronous handling) | NORMAL | GitHub retries or drops the delivery; redelivery causes duplicate work | Minor | Remote | Acceptable | REQ-NF-002 | Acceptable with fast ACK and asynchronous queue |
| HAZ-003 | SYS-002 | Trigger filter over-triggers (non-managed repos, denylist not applied) | NORMAL | Unwanted reviews posted to repos outside `repo_config` | Serious | Occasional | Undesirable | REQ-002, REQ-003 | Tolerable with `repo_config` allow and denylist enforcement |
| HAZ-004 | SYS-002 | Trigger filter misses events (`synchronize` / `review_requested` dropped) | NORMAL | New head SHAs never reviewed; reviews go stale | Serious | Remote | Undesirable | REQ-002, REQ-004 | Tolerable with periodic reconcile sweep |
| HAZ-005 | SYS-003 | Deduplication failure on (repo, PR, head, model) | NORMAL | Duplicate reviews posted for the same head SHA | Minor | Occasional | Tolerable | REQ-004, REQ-012 | Acceptable with unique index and idempotency marker |
| HAZ-006 | SYS-003 | Crash mid-run leaves an orphaned lock | NORMAL | Run stalls permanently; future runs blocked; no review posted | Serious | Remote | Undesirable | REQ-NF-005 | Tolerable with crash-safe recovery and advisory DB state |
| HAZ-007 | SYS-003 | CI gate waits indefinitely for a pending run | NORMAL | Reviews stall; PR author receives no update | Serious | Remote | Undesirable | REQ-010, REQ-014 | Tolerable with gate timeout and partial-report comment |
| HAZ-008 | SYS-004 | Clone or workspace failure (auth, network, disk cap) | NORMAL | Run aborts; review cannot proceed | Serious | Remote | Undesirable | REQ-005, REQ-014 | Tolerable with retry/backoff and partial-report |
| HAZ-009 | SYS-004 | Stale checkout — head SHA not fetched before review | NORMAL | Review comments on outdated code; misleading findings | Critical | Remote | Undesirable | REQ-004, REQ-005 | Tolerable with incremental fetch to head SHA |
| HAZ-010 | SYS-005 | Docs folder absent or unreadable and degradation not recorded | NORMAL | Review runs without docs context; degradation invisible in audit trail | Minor | Remote | Acceptable | REQ-006, REQ-015 | Acceptable with no-docs degradation recorded |
| HAZ-011 | SYS-006 | opencode run subprocess hangs or exits non-zero | NORMAL | Review never completes; PR author uninformed | Serious | Occasional | Undesirable | REQ-007, REQ-014 | Tolerable with timeout, retry, and partial-report |
| HAZ-012 | SYS-006 | Prompt injection via reviewed repo content or skills | NORMAL | Agent induced to perform unintended actions | Critical | Remote | Undesirable | REQ-007, REQ-CN-004 | Tolerable with read-only enforcement and single review session |
| HAZ-013 | SYS-007 | Scope/test compliance validation false positives or negatives | NORMAL | Misleading change-discipline findings in the review summary | Minor | Occasional | Tolerable | REQ-008 | Acceptable with advisory compliance findings |
| HAZ-014 | SYS-008 | gitleaks misses a secret (false negative) exposed in review output | NORMAL | Credentials leaked into review comments visible to repo users | Critical | Remote | Undesirable | REQ-009, REQ-NF-004 | Tolerable with LLM security review and secret hygiene |
| HAZ-015 | SYS-008 | CI failure log fetch fails | NORMAL | Root-cause diagnosis comment missing or incorrect | Serious | Remote | Undesirable | REQ-010, REQ-014 | Tolerable with degraded diagnosis and retry |
| HAZ-016 | SYS-009 | Review posted on retry without state update (double post) | NORMAL | Duplicate review comments on the same PR | Minor | Remote | Acceptable | REQ-011, REQ-012, REQ-NF-005 | Acceptable with posting-transaction and idempotency marker |
| HAZ-017 | SYS-009 | Review posted with an event other than `COMMENT` | NORMAL | Hard-blocking semantics (approve/request-changes) instead of advisory prose | Minor | Remote | Acceptable | REQ-012 | Acceptable with `COMMENT`-only enforcement |
| HAZ-018 | SYS-010 | Unknown or disabled model alias resolved to a wrong provider | NORMAL | Unexpected provider/model used; run fails unexpectedly | Serious | Remote | Undesirable | REQ-013, REQ-016 | Tolerable with alias validation and help reply |
| HAZ-019 | SYS-011 | Malformed `@review` command receives no reply | NORMAL | User gets no feedback; command silently dropped | Minor | Remote | Acceptable | REQ-013 | Acceptable with help reply for unknown/malformed commands |
| HAZ-020 | SYS-011 | Non-command comment text parsed as a command | NORMAL | Unintended review trigger or model override | Serious | Remote | Undesirable | REQ-013 | Tolerable with strict command grammar |
| HAZ-021 | SYS-012 | SQLite corruption or lost update on the dedup key | NORMAL | Duplicate reviews or lost run records | Serious | Remote | Undesirable | REQ-IF-005, REQ-NF-005 | Tolerable with transactions, unique index, and crash recovery |
| HAZ-022 | SYS-013 | Invalid config accepted at boot (not fail-closed) | NORMAL | Service starts misconfigured; reviews misrouted | Critical | Remote | Undesirable | REQ-IF-004, REQ-016 | Tolerable with fail-closed boot validation |
| HAZ-023 | SYS-013 | Secrets (PAT, provider keys) written to config or logs | NORMAL | Credential exposure in repo, logs, or review output | Catastrophic | Remote | Undesirable | REQ-NF-004, REQ-CN-002 | Tolerable with gitignored `.env`, `env_file`, and `auth.json` built at boot |
| HAZ-024 | SYS-014 | GitHub rate limit (403/429) not handled with backoff | NORMAL | Reviews stall during bursts; token suspension risk | Serious | Occasional | Undesirable | REQ-NF-003, REQ-014 | Tolerable with exponential backoff and jitter |
| HAZ-025 | SYS-014 | Review agent writes to the reviewed repository (push/commit) | NORMAL | Unauthorized changes to the target repo | Critical | Remote | Undesirable | REQ-CN-004 | Tolerable with read-only enforcement |
| HAZ-026 | SYS-014 | Structured log / run-record loss on crash | NORMAL | Audit trail gaps; debugging and compliance harmed | Minor | Remote | Acceptable | REQ-015, REQ-NF-007 | Acceptable with persisted run records and `.runs/` |
| HAZ-027 | SYS-006 | Model provider outage mid-run | NORMAL | Review incomplete; PR author uninformed | Serious | Remote | Undesirable | REQ-013, REQ-014 | Tolerable with retry and partial-report |

## Progressive Deepening (Architecture-Level)

No additional architecture-level hazards identified beyond the system-level register above.
Architecture-specific failure modes (interface mismatches, protocol failures, data-format
incompatibilities) are covered at the integration-test level (`ITP-NNN-X` → `ITS-NNN-X#`)
in `integration-test.md`; none introduces a risk that is not already mitigated by the
REQ/SYS controls listed in the register.

## Coverage Summary

| Metric | Count |
|--------|-------|
| Total System Components (SYS) | 14 (14 active, 0 deprecated) |
| Components with ≥1 HAZ | 14 / 14 (100%) (active items only) |
| Total Hazards (HAZ) | 27 |
| System-level hazards | 27 |
| Architecture-level hazards | 0 (progressive deepening) |

### Severity Distribution

| Severity | Count | Percentage |
|----------|-------|------------|
| Catastrophic | 1 | 4% |
| Critical | 6 | 22% |
| Serious | 12 | 44% |
| Minor | 8 | 30% |
| Negligible | 0 | 0% |

### Risk Level Distribution

| Risk Level | Count | Percentage |
|------------|-------|------------|
| Unacceptable | 0 | 0% |
| Undesirable | 19 | 70% |
| Tolerable | 2 | 7% |
| Acceptable | 6 | 22% |

### Operational State Distribution

| State | Hazard Count |
|-------|-------------|
| NORMAL | 27 |
| ALL | 0 |

## Uncovered Components

None — full coverage achieved.
