---

description: "Task list template for feature implementation"

---

# Tasks: GitHub PR Review Agent

<!-- v-model:traces
  requirements: [REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-006, REQ-007, REQ-008, REQ-009, REQ-010, REQ-011, REQ-012, REQ-013, REQ-014, REQ-015, REQ-016, REQ-017, REQ-018, REQ-019, REQ-020, REQ-021, REQ-022, REQ-023, REQ-NF-001, REQ-NF-002, REQ-NF-003, REQ-NF-004, REQ-NF-005, REQ-NF-006, REQ-NF-007, REQ-IF-001, REQ-IF-002, REQ-IF-003, REQ-IF-004, REQ-IF-005, REQ-IF-006, REQ-CN-001, REQ-CN-002, REQ-CN-003, REQ-CN-004]
  system:       [SYS-001, SYS-002, SYS-003, SYS-004, SYS-005, SYS-006, SYS-007, SYS-008, SYS-009, SYS-010, SYS-011, SYS-012, SYS-013, SYS-014]
  architecture: [ARCH-001, ARCH-002, ARCH-003, ARCH-004, ARCH-005, ARCH-006, ARCH-007, ARCH-008, ARCH-009, ARCH-010, ARCH-011, ARCH-012, ARCH-013]
  modules:      [MOD-001, MOD-002, MOD-003, MOD-004, MOD-005, MOD-006, MOD-007, MOD-008, MOD-009, MOD-010, MOD-011, MOD-012, MOD-013, MOD-014, MOD-015, MOD-016, MOD-017, MOD-018, MOD-019]
  version:      v0.7.0
-->

<!-- v-model: hazard-driven elevation skipped — hazard-analysis.md missing/empty -->

**Input**: Design documents from `/specs/001-pr-reviewer-agent/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: The V-Model test plans (acceptance-plan.md, system-test.md, integration-test.md, unit-test.md) are the source of truth for the test tasks below.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/` at repository root
- **Web app**: `backend/src/`, `frontend/src/`
- **Mobile**: `api/src/`, `ios/src/` or `android/src/`
- Paths shown below assume single project - adjust based on plan.md structure

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Create project structure per plan.md (single Python/FastAPI package: `src/`, `tests/unit/`, `tests/integration/`, `tests/system/`, `tests/fixtures/`) <!-- traces-to: MOD-016 → ARCH-012 → SYS-013 → REQ-IF-004 -->
- [ ] T002 Initialize Python/FastAPI project with `pyproject.toml`, and test runner (pytest + pytest-asyncio) <!-- traces-to: MOD-016 → ARCH-012 → SYS-013 → REQ-IF-004 -->
- [ ] T003 [P] Configure linting and formatting tools (ruff) <!-- traces-to: MOD-016 → ARCH-012 → SYS-013 → REQ-IF-004 -->
- [ ] T004 [P] Add `config.yaml` skeleton with providers (`free`/`go`, `gemini` disabled), `repo_config`, denylist, defaults, concurrency, CI-gate settings, docs location (`specs_docs_dir`), `workspace_cache_dir`, `agent_skill_set` <!-- traces-to: MOD-016 → ARCH-012 → SYS-013 → REQ-CN-001 -->
- [ ] T005 [P] Add `Dockerfile` + `docker-compose.yml` with the app + `ngrok/ngrok` sidecar, isolated workspace volume (`/var/agent_cache`), `.env` secret wiring (`env_file`), and boot-time `auth.json` construction from `OPENCODE_GO_TOKEN` <!-- traces-to: MOD-016 → ARCH-012 → SYS-013 → REQ-CN-001 -->

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T006 Setup SQLite schema and migrations: `review_runs`, `repos`, `model_aliases`, `repo_config` per `data-model.md` and `contracts/sqlite-state.md` <!-- traces-to: MOD-015 → ARCH-011 → SYS-012 → REQ-IF-005 -->
- [ ] T007 [P] Implement Config Validator (MOD-016) — load + validate `config.yaml` fail-closed in `src/config/validator.py` <!-- traces-to: MOD-016 → ARCH-012 → SYS-013 → REQ-IF-004 -->
- [ ] T008 [P] Implement Logger & Run Records (MOD-017) — structured JSON logs + `.runs/` persistence in `src/runtime/logger.py` <!-- traces-to: MOD-017 → ARCH-013 → SYS-014 → REQ-NF-007 -->
- [ ] T009 [P] Implement GitHub Client (MOD-013) — typed REST client with PAT (`repo` scope) auth, webhook management, & CI job log fetch in `src/github/client.py` <!-- traces-to: MOD-013 → ARCH-009 → SYS-009 → REQ-IF-001 -->
- [ ] T010 Implement Rate Limiter (MOD-018) — central 403/429 backoff policy in `src/runtime/rate-limiter.py` <!-- traces-to: MOD-018 → ARCH-013 → SYS-014 → REQ-NF-003 -->
- [ ] T011 [P] Configure error handling and retry infrastructure with exponential backoff <!-- traces-to: MOD-004 → ARCH-003 → SYS-003 → REQ-NF-005 -->
- [ ] T012 Setup environment configuration management (gitignored `.env` via `env_file`; container builds `auth.json` from `OPENCODE_GO_TOKEN` at boot, REQ-NF-004) <!-- traces-to: MOD-013 → ARCH-009 → SYS-014 → REQ-NF-004 -->

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - [Title] (Priority: P1) 🎯 MVP

**Goal**: Auto-review on my PRs — webhook → trigger → clone → docs → security + scope & test validation + OpenCode HTTP API → formal review posted.

**Independent Test**: Open a PR from my account on a repo; verify a formal review with summary, scope check, and security analysis is posted.

### Tests for User Story 1 (OPTIONAL - only if tests requested) ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T013 [P] [US1] Unit tests for Webhook Handler (MOD-001): UTP-001-A in `tests/unit/test_webhook.py` <!-- traces-to: MOD-001 → ARCH-001 → SYS-001 → REQ-001 -->
- [ ] T014 [P] [US1] Unit tests for Trigger Decision Engine (MOD-002): UTP-002-A in `tests/unit/test_trigger.py` <!-- traces-to: MOD-002 → ARCH-002 → SYS-002 → REQ-002 -->
- [ ] T015 [P] [US1] Unit tests for Queue Manager (MOD-004) + Worker Scheduler (MOD-005): UTP-004-A, UTP-005-A in `tests/unit/test_queue.py` <!-- traces-to: MOD-004 → ARCH-003 → SYS-003 → REQ-004 -->
- [ ] T016 [P] [US1] Unit tests for Clone Cache Manager (MOD-006): UTP-006-A in `tests/unit/test_clone-cache.py` <!-- traces-to: MOD-006 → ARCH-004 → SYS-004 → REQ-005 -->
- [ ] T017 [P] [US1] Unit tests for Docs Loader (MOD-007): UTP-007-A in `tests/unit/test_docs-loader.py` <!-- traces-to: MOD-007 → ARCH-005 → SYS-005 → REQ-006 -->
- [ ] T018 [P] [US1] Unit tests for opencode subprocess runner (MOD-008): UTP-008-A in `tests/unit/test_workspace.py` <!-- traces-to: MOD-008 → ARCH-006 → SYS-006 → REQ-IF-003 -->
- [ ] T019 [P] [US1] Unit tests for PR Scope & Test Compliance Validator (MOD-010): UTP-010-A in `tests/unit/test_scope_validator.py` <!-- traces-to: MOD-010 → ARCH-007 → SYS-007 → REQ-008 -->
- [ ] T020 [P] [US1] Unit tests for Security Scan Runner (MOD-011) + LLM Security Reviewer (MOD-012): UTP-011-A, UTP-012-A in `tests/unit/test_security.py` <!-- traces-to: MOD-011 → ARCH-008 → SYS-008 → REQ-009 -->
- [ ] T021 [P] [US1] Unit tests for State Repository (MOD-015): UTP-015-A in `tests/unit/test_state.py` <!-- traces-to: MOD-015 → ARCH-011 → SYS-012 → REQ-NF-005 -->

### Implementation for User Story 1

- [ ] T022 [P] [US1] Implement Webhook Handler (MOD-001) in `src/webhook/handler.py` (depends on T021, T011) <!-- traces-to: MOD-001 → ARCH-001 → SYS-001 → REQ-001 -->
- [ ] T023 [P] [US1] Implement Trigger Decision Engine (MOD-002) in `src/webhook/trigger.py` (depends on T022) <!-- traces-to: MOD-002 → ARCH-002 → SYS-002 → REQ-002 -->
- [ ] T024 [P] [US1] Implement Queue Manager (MOD-004) in `src/pipeline/queue.py` (depends on T021) <!-- traces-to: MOD-004 → ARCH-003 → SYS-003 → REQ-004 -->
- [ ] T025 [P] [US1] Implement Worker Scheduler (MOD-005) in `src/pipeline/scheduler.py` (depends on T024) <!-- traces-to: MOD-005 → ARCH-003 → SYS-003 → REQ-NF-006 -->
- [ ] T026 [P] [US1] Implement Clone Cache Manager (MOD-006) in `src/clone-cache/manager.py` <!-- traces-to: MOD-006 → ARCH-004 → SYS-004 → REQ-005 -->
- [ ] T027 [P] [US1] Implement Docs Loader (MOD-007) in `src/docs-loader/loader.py` <!-- traces-to: MOD-007 → ARCH-005 → SYS-005 → REQ-006 -->
- [ ] T028 [P] [US1] Implement opencode subprocess runner (MOD-008) in `src/executor/runner.py` (one-off `opencode run` CLI subprocess with structured-JSON output contract; depends on T026, T027) <!-- traces-to: MOD-008 → ARCH-006 → SYS-006 → REQ-IF-003 -->
- [ ] T029 [P] [US1] Implement PR Scope & Editor-Agnostic Test Compliance Validator (MOD-010) in `src/scope-validator/validator.py` (fetching linked issue context via GitHub REST API) <!-- traces-to: MOD-010 → ARCH-007 → SYS-007 → REQ-007, REQ-008 -->
- [ ] T030 [P] [US1] Implement CI Gate Monitor (MOD-009) in `src/ci-debugger/debugger.py` (settle window, gate polling of `check_run`/`workflow_run`, wait cap, fetching GitHub check logs, root-cause diagnosis) <!-- traces-to: MOD-009 → ARCH-008 → SYS-008 → REQ-010 -->
- [ ] T031 [P] [US1] Implement Security Scan Runner (MOD-011) in `src/security/scanner.py` (gitleaks full-checkout on green heads) <!-- traces-to: MOD-011 → ARCH-008 → SYS-008 → REQ-009 -->
- [ ] T031a [P] [US1] Implement Stage 2 Validator Filter (FR-016) in `src/pipeline/validator_filter.py` (stripping superficial nitpicks and low-confidence findings before submission) <!-- traces-to: MOD-013 → ARCH-009 → SYS-009 → REQ-011 -->
- [ ] T032 [US1] Wire pipeline end-to-end in `src/main.py`: webhook → queue → scheduler → CI gate → executor → validator filter → COMMENT-only submission (depends on T022-T031a) <!-- traces-to: MOD-004 → ARCH-003 → SYS-003 → REQ-011, REQ-012 -->
- [ ] T033 [US1] Run unit tests and make them green (UTP-001-A .. UTP-019-A) <!-- traces-to: MOD-001 → ARCH-001 → SYS-001 → REQ-001 -->
- [ ] T034 [P] [US1] Integration test: receiver wired to config secret and trigger filter (ITP-001-A) in `tests/integration/test_webhook.py` <!-- traces-to: MOD-001 → ARCH-001 → SYS-001 → REQ-001 -->
- [ ] T035 [P] [US1] Integration test: enqueue persists before ack; full pipeline completes (ITP-003-A) in `tests/integration/test_pipeline.py` <!-- traces-to: MOD-004 → ARCH-003 → SYS-003 → REQ-004 -->
- [ ] T036 [P] [US1] Integration test: scope validation + CI gate produce normalized findings (ITP-007-A, ITP-006-A) in `tests/integration/test_phases.py` <!-- traces-to: MOD-010 → ARCH-007 → SYS-007 → REQ-008 -->
- [ ] T037 [P] [US1] Integration test: state store recovers orphans on boot (ITP-011-A) in `tests/integration/test_state.py` <!-- traces-to: MOD-015 → ARCH-011 → SYS-012 → REQ-NF-005 -->
- [ ] T038 [US1] Run integration tests and make them green (ITP-001-A .. ITP-013-A) <!-- traces-to: MOD-004 → ARCH-003 → SYS-003 → REQ-004 -->
- [ ] T039 [P] [US1] System test: signature gate + fast ACK (STP-001-A/B) in `tests/system/test_webhook.py` <!-- traces-to: MOD-001 → ARCH-001 → SYS-001 → REQ-NF-002 -->
- [ ] T040 [P] [US1] System test: dedup, concurrency bound, retry (STP-003-A) in `tests/system/test_pipeline.py` <!-- traces-to: MOD-005 → ARCH-003 → SYS-003 → REQ-NF-006 -->
- [ ] T041 [P] [US1] System test: clone/update/evict lifecycle (STP-004-A) in `tests/system/test_clone-cache.py` <!-- traces-to: MOD-006 → ARCH-004 → SYS-004 → REQ-005 -->
- [ ] T042 [P] [US1] System test: one-off opencode CLI execution contract (STP-006-A) in `tests/system/test_executor.py` <!-- traces-to: MOD-008 → ARCH-006 → SYS-006 → REQ-IF-003 -->
- [ ] T043 [P] [US1] System test: scope validation + CI gate (STP-007-A, STP-006-B) in `tests/system/test_phases.py` <!-- traces-to: MOD-010 → ARCH-007 → SYS-007 → REQ-008 -->
- [ ] T044 [P] [US1] System test: review submission and state update (STP-009-A) in `tests/system/test_report.py` <!-- traces-to: MOD-013 → ARCH-009 → SYS-009 → REQ-011 -->
- [ ] T045 [US1] Run system tests and make them green (STP-001-A .. STP-014-B) <!-- traces-to: MOD-005 → ARCH-003 → SYS-003 → REQ-004 -->
- [ ] T046 [P] [US1] Acceptance test: webhook signature + author trigger + review posted (ATP-001-A, ATP-002-A, ATP-011-A) in `tests/acceptance/test_e2e.py` <!-- traces-to: MOD-001 → ARCH-001 → SYS-001 → REQ-001 -->
- [ ] T047 [US1] Run acceptance tests and make them green (ATP-001-A .. ATP-NF-007-A) <!-- traces-to: MOD-013 → ARCH-009 → SYS-009 → REQ-011 -->

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - [Title] (Priority: P2)

**Goal**: Review when I am tagged as reviewer — `review_requested` trigger behaves identically to the author trigger.

**Independent Test**: Request review from my account on a PR; verify a review is posted with the same content contract.

### Tests for User Story 2 (OPTIONAL - only if tests requested) ⚠️

- [ ] T048 [P] [US2] Unit test for Trigger Decision Engine reviewer branch: UTP-002-A (decision matrix boundaries) in `tests/unit/test_trigger.py` <!-- traces-to: MOD-002 → ARCH-002 → SYS-002 → REQ-002 -->

### Implementation for User Story 2

- [ ] T049 [US2] Extend Trigger Decision Engine (MOD-002) to include `review_requested` in `src/webhook/trigger.py` (depends on T023) <!-- traces-to: MOD-002 → ARCH-002 → SYS-002 → REQ-002 -->
- [ ] T050 [US2] Run unit tests (UTP-002-A) <!-- traces-to: MOD-002 → ARCH-002 → SYS-002 → REQ-002 -->
- [ ] T051 [US2] Integration test: trigger decision + dedup for reviewer flow (ITP-002-A, ITP-003-B) in `tests/integration/test_trigger.py` <!-- traces-to: MOD-002 → ARCH-002 → SYS-002 → REQ-002 -->
- [ ] T052 [US2] Run integration tests (ITP-002-A) <!-- traces-to: MOD-002 → ARCH-002 → SYS-002 → REQ-002 -->
- [ ] T053 [US2] System test: trigger + managed-repo decision matrix incl. reviewer (STP-002-A) in `tests/system/test_trigger.py` <!-- traces-to: MOD-002 → ARCH-002 → SYS-002 → REQ-003 -->
- [ ] T054 [US2] Run system tests (STP-002-A) <!-- traces-to: MOD-002 → ARCH-002 → SYS-002 → REQ-002 -->
- [ ] T055 [US2] Acceptance test: `review_requested` trigger posts a review, deduped at head (ATP-002-A SCN-002-A2) <!-- traces-to: MOD-002 → ARCH-002 → SYS-002 → REQ-002 -->
- [ ] T056 [US2] Run acceptance tests (ATP-002-A) <!-- traces-to: MOD-002 → ARCH-002 → SYS-002 → REQ-002 -->

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - [Title] (Priority: P3)

**Goal**: Per-review model selection via `@review --model <alias>` comment command, with default fallback and unknown-alias help reply. *(Real priority: P2 per spec.md — the H2 text is pinned byte-identical to the template.)*

**Independent Test**: Comment `@review --model go` on a PR and verify the review was generated with the `go` provider (opencode-go).

### Tests for User Story 3 (OPTIONAL - only if tests requested) ⚠️

- [ ] T057 [P] [US3] Unit tests for Command Parser (MOD-003): UTP-003-A in `tests/unit/test_command-parser.py` <!-- traces-to: MOD-003 → ARCH-002 → SYS-011 → REQ-013 -->
- [ ] T058 [P] [US3] Unit tests for Model Resolver (MOD-014): UTP-014-A in `tests/unit/test_model-resolver.py` <!-- traces-to: MOD-014 → ARCH-010 → SYS-010 → REQ-013 -->

### Implementation for User Story 3

- [ ] T059 [P] [US3] Implement Command Parser (MOD-003) in `src/models/command-parser.py` <!-- traces-to: MOD-003 → ARCH-002 → SYS-011 → REQ-013 -->
- [ ] T060 [P] [US3] Implement Model Resolver (MOD-014) in `src/models/resolver.py` (depends on T007) <!-- traces-to: MOD-014 → ARCH-010 → SYS-010 → REQ-013 -->
- [ ] T061 [US3] Wire command → re-enqueue with model override in `src/webhook/trigger.py` (depends on T059, T060) <!-- traces-to: MOD-003 → ARCH-002 → SYS-011 → REQ-013 -->
- [ ] T062 [US3] Run unit tests (UTP-003-A, UTP-014-A) <!-- traces-to: MOD-014 → ARCH-010 → SYS-010 → REQ-013 -->
- [ ] T063 [US3] Integration test: model resolution wired to run records (ITP-010-A) in `tests/integration/test_model.py` <!-- traces-to: MOD-014 → ARCH-010 → SYS-010 → REQ-013 -->
- [ ] T064 [US3] Run integration tests (ITP-010-A) <!-- traces-to: MOD-014 → ARCH-010 → SYS-010 → REQ-013 -->
- [ ] T065 [P] [US3] System test: alias resolution + comment command parsing (STP-010-A, STP-011-A) in `tests/system/test_model.py` <!-- traces-to: MOD-014 → ARCH-010 → SYS-010 → REQ-013 -->
- [ ] T066 [US3] Run system tests (STP-010-A, STP-011-A) <!-- traces-to: MOD-014 → ARCH-010 → SYS-010 → REQ-013 -->
- [ ] T067 [US3] Acceptance test: `@review --model go` runs with opencode-go; unknown/disabled alias (`gemini`) replies with help (ATP-013-A) <!-- traces-to: MOD-014 → ARCH-010 → SYS-010 → REQ-013 -->
- [ ] T068 [US3] Run acceptance tests (ATP-013-A) <!-- traces-to: MOD-014 → ARCH-010 → SYS-010 → REQ-013 -->
- [ ] T104 [P] [US3] Unit tests for Model Registry fallback + `switch_default`: UTP-014-B in `tests/unit/test_model-resolver.py` <!-- traces-to: MOD-014 → ARCH-010 → SYS-010 → REQ-016 -->
- [ ] T105 [US3] Implement Model Registry `switch_default` fallback on 403/429 (MOD-014) in `src/models/resolver.py` (depends on T060) <!-- traces-to: MOD-014 → ARCH-010 → SYS-010 → REQ-016 -->
- [ ] T106 [US3] Run unit tests (UTP-014-B) <!-- traces-to: MOD-014 → ARCH-010 → SYS-010 → REQ-016 -->
- [ ] T107 [US3] Integration test: credit-exhaustion fallback resolution (ITP-010-A3) in `tests/integration/test_model.py` <!-- traces-to: MOD-014 → ARCH-010 → SYS-010 → REQ-016 -->
- [ ] T108 [US3] Run integration tests (ITP-010-A3) <!-- traces-to: MOD-014 → ARCH-010 → SYS-010 → REQ-016 -->
- [ ] T109 [US3] System test: `switch_default` + per-PR override preserved (STP-010-A3) in `tests/system/test_model.py` <!-- traces-to: MOD-014 → ARCH-010 → SYS-010 → REQ-016 -->
- [ ] T110 [US3] Run system tests (STP-010-A3) <!-- traces-to: MOD-014 → ARCH-010 → SYS-010 → REQ-016 -->
- [ ] T111 [US3] Acceptance test: single app-layer model definition, config-only switch, per-PR override preserved (ATP-016-A) <!-- traces-to: MOD-014 → ARCH-010 → SYS-010 → REQ-016 -->
- [ ] T112 [US3] Run acceptance tests (ATP-016-A) <!-- traces-to: MOD-014 → ARCH-010 → SYS-010 → REQ-016 -->

**Checkpoint**: At this point, User Stories 1, 2 AND 3 should all work independently

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

### User Story 4 - Repo-scoped and vendored skills (P2)

**Goal**: Agent runs with repo `AGENTS.md` + `.opencode/` skills, the vendored `.agents/skills/` set in the image, the defined `agent_skill_set`, and `specs/<owner>/<repo>/` docs as context; reviews only green heads (CI gate).

- [ ] T069 [P] [US4] Unit tests for Workspace Runner skills/docs injection: UTP-007-A, UTP-008-A in `tests/unit/test_workspace.py` <!-- traces-to: MOD-008 → ARCH-006 → SYS-006 → REQ-007 -->
- [ ] T070 [P] [US4] Implement CI Gate Monitor (MOD-009) in `src/ci-debugger/debugger.py` (settle window, gate polling of `check_run`/`workflow_run`, wait cap, fetching GitHub check logs, root-cause diagnosis comment) <!-- traces-to: MOD-009 → ARCH-008 → SYS-008 → REQ-010 -->
- [ ] T071 [US4] Wire docs + skills injection into Workspace Runner (MOD-008) in `src/executor/runner.py` (depends on T028, T070) <!-- traces-to: MOD-008 → ARCH-006 → SYS-006 → REQ-007 -->
- [ ] T072 [US4] Run unit tests (UTP-007-A, UTP-008-A, UTP-009-A) <!-- traces-to: MOD-008 → ARCH-006 → SYS-006 → REQ-007 -->
- [ ] T073 [US4] Integration test: CI gate failure → diagnosis comment, no review (ITP-006-A) in `tests/integration/test_ci_debugger.py` <!-- traces-to: MOD-009 → ARCH-008 → SYS-008 → REQ-010 -->
- [ ] T074 [US4] Run integration tests (ITP-006-A) <!-- traces-to: MOD-008 → ARCH-006 → SYS-006 → REQ-007 -->
- [ ] T075 [US4] System test: CI gate outcome (STP-006-B); docs load + degradation (STP-005-A/B) in `tests/system/test_executor.py` <!-- traces-to: MOD-009 → ARCH-008 → SYS-008 → REQ-010 -->
- [ ] T076 [US4] Run system tests (STP-005-A/B, STP-006-B) <!-- traces-to: MOD-008 → ARCH-006 → SYS-006 → REQ-007 -->
- [ ] T077 [US4] Acceptance test: skills + docs context, CI gate (ATP-007-A, ATP-006-A, ATP-010-A) <!-- traces-to: MOD-008 → ARCH-006 → SYS-006 → REQ-007 -->
- [ ] T078 [US4] Run acceptance tests (ATP-006-A, ATP-007-A, ATP-010-A) <!-- traces-to: MOD-008 → ARCH-006 → SYS-006 → REQ-007 -->
- [ ] T113 [P] [US4] Unit tests for Skill Set Selector: UTP-019-A in `tests/unit/test_skills.py` <!-- traces-to: MOD-019 → ARCH-006 → SYS-006 → REQ-017 -->
- [ ] T114 [US4] Implement Skill Set Selector (MOD-019) in `src/executor/skills.py` (depends on T071) <!-- traces-to: MOD-019 → ARCH-006 → SYS-006 → REQ-017 -->
- [ ] T115 [US4] Run unit tests (UTP-019-A) <!-- traces-to: MOD-019 → ARCH-006 → SYS-006 → REQ-017 -->
- [ ] T116 [US4] Integration test: base + situational skill selection (ITP-006-A2) in `tests/integration/test_executor.py` <!-- traces-to: MOD-019 → ARCH-006 → SYS-006 → REQ-017 -->
- [ ] T117 [US4] Run integration tests (ITP-006-A2) <!-- traces-to: MOD-019 → ARCH-006 → SYS-006 → REQ-017 -->
- [ ] T118 [US4] System test: defined skill set injected into run (STP-006-A3) in `tests/system/test_executor.py` <!-- traces-to: MOD-019 → ARCH-006 → SYS-006 → REQ-017 -->
- [ ] T119 [US4] Run system tests (STP-006-A3) <!-- traces-to: MOD-019 → ARCH-006 → SYS-006 → REQ-017 -->
- [ ] T120 [US4] Acceptance test: defined agent skill set per review (ATP-017-A) <!-- traces-to: MOD-019 → ARCH-006 → SYS-006 → REQ-017 -->
- [ ] T121 [US4] Run acceptance tests (ATP-017-A) <!-- traces-to: MOD-019 → ARCH-006 → SYS-006 → REQ-017 -->

### User Story 5 - Re-review on new commits (P2)

**Goal**: New head SHA produces a new review; near-simultaneous duplicates coalesce.

- [ ] T079 [P] [US5] Unit tests for Queue Manager re-review coalescing: UTP-004-A (enqueue boundaries) in `tests/unit/test_queue.py` <!-- traces-to: MOD-004 → ARCH-003 → SYS-003 → REQ-004 -->
- [ ] T080 [US5] Implement re-review scheduling in Worker Scheduler (MOD-005) in `src/pipeline/scheduler.py` (depends on T025) <!-- traces-to: MOD-005 → ARCH-003 → SYS-003 → REQ-004 -->
- [ ] T081 [US5] Run unit tests (UTP-004-A, UTP-005-A) <!-- traces-to: MOD-004 → ARCH-003 → SYS-003 → REQ-004 -->
- [ ] T082 [US5] Integration test: dedup, re-review, retry (ITP-003-B) in `tests/integration/test_pipeline.py` <!-- traces-to: MOD-004 → ARCH-003 → SYS-003 → REQ-004 -->
- [ ] T083 [US5] Run integration tests (ITP-003-B) <!-- traces-to: MOD-004 → ARCH-003 → SYS-003 → REQ-004 -->
- [ ] T084 [US5] System test: dedup at head, re-review on synchronize (STP-003-A) in `tests/system/test_pipeline.py` <!-- traces-to: MOD-004 → ARCH-003 → SYS-003 → REQ-004 -->
- [ ] T085 [US5] Run system tests (STP-003-A) <!-- traces-to: MOD-004 → ARCH-003 → SYS-003 → REQ-004 -->
- [ ] T086 [US5] Acceptance test: no duplicate at same head; new review at new head (ATP-004-A SCN-004-A1/A2) <!-- traces-to: MOD-004 → ARCH-003 → SYS-003 → REQ-004 -->
- [ ] T087 [US5] Run acceptance tests (ATP-004-A) <!-- traces-to: MOD-004 → ARCH-003 → SYS-003 → REQ-004 -->

### User Story 6 - Always-COMMENT advisory reviews and failure reporting (P3)

**Goal**: Always-COMMENT reviews (advisory by design, never APPROVE/REQUEST_CHANGES) with marker-anchored dedup; retry with backoff; partial-report on non-completable reviews.

- [ ] T088 [P] [US6] Unit tests for always-COMMENT submission + backoff boundary: UTP-013-A, UTP-018-A in `tests/unit/test_report.py` <!-- traces-to: MOD-013 → ARCH-009 → SYS-009 → REQ-012 -->
- [ ] T089 [US6] Implement COMMENT-only submission (with `_Reviewed by PR Review Agent · run <run_id>_` marker) in GitHub Client (MOD-013) + Queue Manager (MOD-004) retry/partial-report in `src/github/client.py`, `src/pipeline/queue.py` (depends on T009, T024) <!-- traces-to: MOD-013 → ARCH-009 → SYS-009 → REQ-012 -->
- [ ] T090 [US6] Run unit tests (UTP-013-A, UTP-018-A) <!-- traces-to: MOD-013 → ARCH-009 → SYS-009 → REQ-012 -->
- [ ] T091 [US6] Integration test: config failure halts boot (ITP-012-A); runtime signals + secret hygiene (ITP-013-A) in `tests/integration/test_runtime.py` <!-- traces-to: MOD-013 → ARCH-009 → SYS-014 → REQ-NF-004 -->
- [ ] T092 [US6] Run integration tests (ITP-012-A, ITP-013-A) <!-- traces-to: MOD-013 → ARCH-009 → SYS-009 → REQ-012 -->
- [ ] T093 [US6] System test: always-COMMENT submission (STP-003-B); run records, rate-limit policy, secret hygiene (STP-014-A/B) in `tests/system/test_runtime.py` <!-- traces-to: MOD-013 → ARCH-009 → SYS-009 → REQ-012 -->
- [ ] T094 [US6] Run system tests (STP-003-B, STP-014-A/B) <!-- traces-to: MOD-013 → ARCH-009 → SYS-009 → REQ-012 -->
- [ ] T095 [US6] Acceptance test: COMMENT-only advisory + retry then partial report (ATP-012-A, ATP-014-A) <!-- traces-to: MOD-013 → ARCH-009 → SYS-009 → REQ-012 -->
- [ ] T096 [US6] Run acceptance tests (ATP-012-A, ATP-014-A) <!-- traces-to: MOD-013 → ARCH-009 → SYS-009 → REQ-012 -->

### Phase N: Observability Enhancement (P1)

**Goal**: High operational visibility — `LoggingConfigurator` (JSON log formatting + `HealthzFilter` 15-min throttle), 20 structured service event types, subprocess log streaming, and compose ngrok logging.

- [ ] T122 [P] [US7] Unit tests for `JsonFormatter` & `HealthzFilter`: `tests/unit/test_json_formatter.py`, `tests/unit/test_healthz_filter.py` <!-- traces-to: MOD-017 → ARCH-013 → SYS-014 → REQ-015, REQ-NF-007 -->
- [ ] T123 [P] [US7] Unit tests for per-service structured event schemas: `tests/unit/test_service_log_events.py` <!-- traces-to: MOD-017 → ARCH-013 → SYS-014 → REQ-015, REQ-NF-007 -->
- [ ] T124 [P] [US7] Implement `LoggingConfigurator`, `JsonFormatter`, and `HealthzFilter` in `src/observability/configurator.py` <!-- traces-to: MOD-017 → ARCH-013 → SYS-014 → REQ-015, REQ-NF-007 -->
- [ ] T125 [US7] Wire `LoggingConfigurator` into `create_app()` in `src/webhook/app.py` <!-- traces-to: MOD-017 → ARCH-013 → SYS-014 → REQ-015, REQ-NF-007 -->
- [ ] T126 [US7] Add structured log calls (`webhook_received`, `webhook_ignored`, `ngrok_url_acquired`, `ngrok_reconcile`, `ngrok_error`) in `src/webhook/handler.py` and `src/webhook/registrar.py` <!-- traces-to: MOD-001, MOD-017 → ARCH-001, ARCH-013 → SYS-001, SYS-014 → REQ-001, REQ-015 -->
- [ ] T127 [US7] Add structured log calls (`github_request`, `github_rate_limited`) in `src/github/client.py` <!-- traces-to: MOD-013, MOD-017 → ARCH-009, ARCH-013 → SYS-009, SYS-014 → REQ-IF-001, REQ-015 -->
- [ ] T128 [US7] Add structured log calls (`opencode_spawn`, `opencode_exit`, `opencode_parse_fallback`, `opencode_parse_ok`) in `src/runner/workspace.py` <!-- traces-to: MOD-008, MOD-017 → ARCH-006, ARCH-013 → SYS-006, SYS-014 → REQ-IF-003, REQ-015 -->
- [ ] T129 [US7] Add structured log calls (`ci_gate_waiting`, `ci_gate_resolved`) in `src/ci/gate.py` <!-- traces-to: MOD-009, MOD-017 → ARCH-008, ARCH-013 → SYS-008, SYS-014 → REQ-010, REQ-015 -->
- [ ] T130 [US7] Add structured log calls (`job_enqueued`, `job_dedup_hit`, `job_state_transition`, `worker_tick`, `job_started`, `job_completed`) in `src/queue/manager.py` and `src/queue/worker.py` <!-- traces-to: MOD-004, MOD-005, MOD-017 → ARCH-003, ARCH-013 → SYS-003, SYS-014 → REQ-004, REQ-015 -->
- [ ] T131 [US7] Add structured log calls (`gitleaks_run`, `llm_security_review`) in `src/security/scanner.py` and `src/security/llm.py` <!-- traces-to: MOD-011, MOD-012, MOD-017 → ARCH-008, ARCH-013 → SYS-008, SYS-014 → REQ-009, REQ-015 -->
- [ ] T132 [US7] Run unit tests for observability (`test_json_formatter.py`, `test_healthz_filter.py`, `test_service_log_events.py`) <!-- traces-to: MOD-017 → ARCH-013 → SYS-014 → REQ-015, REQ-NF-007 -->
- [ ] T133 [US7] Integration test: `/healthz` probe log suppression (15-min window) in `tests/integration/test_healthz_throttle.py` <!-- traces-to: MOD-017 → ARCH-013 → SYS-014 → REQ-015, REQ-NF-007 -->

### Polish & Cross-Cutting

- [ ] T097 [P] Documentation updates in `README.md` (docker compose quick start) <!-- traces-to: MOD-016 → ARCH-012 → SYS-013 → REQ-CN-001 -->
- [ ] T098 Code cleanup and refactoring across `src/`
- [ ] T099 Performance optimization across all stories (clone fetch reuse, parallel phases)
- [ ] T100 [P] Additional unit tests for uncovered branches in `tests/unit/`
- [ ] T101 Security hardening: secret hygiene audit per REQ-NF-004
- [ ] T102 Run quickstart.md validation (Walkthroughs 1-5)
- [ ] T103 Run full V-Model gate: `run-v-model-gate.sh` on all eight artifacts + traceability matrix <!-- traces-to: MOD-017 → ARCH-013 → SYS-014 → REQ-015 -->

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Depends on US1's Trigger Decision Engine (T023); independently testable
- **User Story 3 (P2)**: Can start after Foundational (Phase 2) - Depends on Config Validator (T007); independently testable
- **User Story 4 (P2)**: Depends on US1's Workspace Runner (T028) + CI Gate Monitor (T070)
- **User Story 5 (P2)**: Depends on US1's Queue/Scheduler (T024, T025)
- **User Story 6 (P3)**: Depends on US1's GitHub Client (T009) + Queue (T024)

### Within Each User Story

- Tests (if included) MUST be written and FAIL before implementation
- TDD order per story: write unit tests → implement modules → run unit tests → write integration tests → run integration tests → write system tests → run system tests → write acceptance tests
- Models before services
- Services before endpoints
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, all user stories can start in parallel (if team capacity allows)
- All tests for a user story marked [P] can run in parallel
- Models within a story marked [P] can run in parallel
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together (if tests requested):
Task: "Unit tests for Webhook Handler (MOD-001): UTP-001-A in tests/unit/test_webhook.py"
Task: "Unit tests for Trigger Decision Engine (MOD-002): UTP-002-A in tests/unit/test_trigger.py"
Task: "Unit tests for Queue Manager (MOD-004) + Worker Scheduler (MOD-005): UTP-004-A, UTP-005-A in tests/unit/test_queue.py"

# Launch all models for User Story 1 together:
Task: "Implement Webhook Handler (MOD-001) in src/webhook/handler.py"
Task: "Implement Trigger Decision Engine (MOD-002) in src/webhook/trigger.py"
Task: "Implement Queue Manager (MOD-004) in src/pipeline/queue.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (TDD: tests first, then modules, then integration/system/acceptance)
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1
   - Developer B: User Story 2
   - Developer C: User Story 3
3. Stories complete and integrate independently

---

## Phase 7: User Story 8 - Draft Ingress, Preview Gate & External Webhook Auto-Approval (Priority: P1)

**Goal**: Ingest self-authored Draft PRs, gate review publication behind an out-of-band external webhook preview, support dual-channel approval (`@review approve` / API endpoint), auto-approve & promote Draft PRs on GitHub upon user approval, and auto-cancel/expire stale pending reviews.

- [ ] T051 [P] [US8] Implement User Draft PR Ingress Filtering (MOD-002) in `src/filter/trigger.py` — filter pull_request events so that Draft PRs authored by the self-account are enqueued for review while Draft PRs by other authors are skipped <!-- traces-to: MOD-002 → ARCH-002 → SYS-002 → REQ-018 -->
- [ ] T052 [P] [US8] Implement Slack Block Kit Webhook Notifier (MOD-017) in `src/observability/slack_notifier.py` — format and send Slack Block Kit messages containing review summary preview, run ID, and interactive approval buttons/links to `SLACK_WEBHOOK_URL` when a review reaches `pending_approval` <!-- traces-to: MOD-017 → ARCH-013 → SYS-014 → REQ-019 -->
- [ ] T053 [P] [US8] Implement Staged Review Preview Gate (MOD-004, MOD-015) in `src/executor/pipeline.py` & `src/state/` — hold completed review findings in `pending_approval` state rather than posting directly to GitHub <!-- traces-to: MOD-004 → ARCH-003 → SYS-003 → REQ-020 -->
- [ ] T054 [P] [US8] Implement Dual-Channel Approval Endpoint & Command Handler (MOD-001, MOD-002) in `src/webhook/app.py` & `src/filter/trigger.py` — handle `@review approve` comments and `POST /api/reviews/{run_id}/approve` API requests to release staged reviews <!-- traces-to: MOD-001 → ARCH-001 → SYS-001 → REQ-021 -->
- [ ] T055 [P] [US8] Implement Draft PR Auto-Approval & Promotion (MOD-013) in `src/github/client.py` & `src/executor/pipeline.py` — on approval of a self-authored Draft PR review, submit GitHub review with `event: APPROVE` and call GitHub API (`markPullRequestReadyForReview`) to convert Draft PR to Ready for Review <!-- traces-to: MOD-013 → ARCH-009 → SYS-009 → REQ-022 -->
- [ ] T056 [P] [US8] Implement Stale Invalidation & Expiration Sweeper (MOD-004, MOD-015) in `src/queue/manager.py` & `src/state/` — auto-cancel `pending_approval` reviews when a `synchronize` event arrives for a new head SHA, and expire unapproved reviews after 24 hours <!-- traces-to: MOD-004 → ARCH-003 → SYS-003 → REQ-023 -->

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (TDD RED → GREEN)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
- Every task cites V-Model IDs; the `<!-- traces-to: -->` comments are the V-Model trace bridge (additive-only enrichment, ARCH-008/MOD-012)

## V-Model Trace Summary

| Story | Modules | Test Sources | Status |
|-------|---------|--------------|--------|
| US1 — Auto-review on my PRs | MOD-001, 002, 004, 005, 006, 007, 008, 010, 011, 012, 013, 015 | UTP-001/002/004-008/010-012/015, ITP-001/003/007/008/011, STP-001/003/004/006-009, ATP-001/002/008/009/011 | TDD-ordered, P1 MVP |
| US2 — Review when tagged | MOD-002 | UTP-002, ITP-002/003-B, STP-002, ATP-002 | TDD-ordered, P2 |
| US3 — Per-review model selection | MOD-003, 014 | UTP-003/014, ITP-010, STP-010/011, ATP-013 | TDD-ordered, P2 |
| US4 — Repo-scoped and vendored skills | MOD-008, 009 | UTP-007/008/009, ITP-006, STP-005/006, ATP-006/007/010 | TDD-ordered, P2 |
| US5 — Re-review on new commits | MOD-004, 005 | UTP-004/005, ITP-003-B, STP-003, ATP-004 | TDD-ordered, P2 |
| US6 — Always-COMMENT advisory reviews and failure reporting | MOD-004, 013 | UTP-013/018, ITP-012/013, STP-003-B/014, ATP-012/014 | TDD-ordered, P3 |
| US7 — Observability Enhancement | MOD-001, 004, 005, 006, 008, 009, 011, 012, 013, 017 | test_json_formatter, test_healthz_filter, test_service_log_events, test_healthz_throttle | TDD-ordered, P1 |
| US8 — Draft Ingress, Preview Gate & External Webhook Auto-Approval | MOD-001, 002, 004, 013, 015, 017 | test_draft_ingress, test_webhook_notifier, test_approval_gate, test_auto_approve | TDD-ordered, P1 |

Hazard-driven elevation skipped — `hazard-analysis.md` absent. Full traceability via `v-model/traceability-matrix.md` (all four matrices 100%, no gaps).
