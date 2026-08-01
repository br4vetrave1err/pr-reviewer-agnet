# Feature Specification: GitHub PR Review Agent

**Feature Branch**: `001-pr-reviewer-agent`

**Created**: 2026-08-01

**Status**: Draft

**Input**: User description: "A PR reviewer agent that continuously runs in Docker. It triggers whenever I raise a PR from my GitHub account or whenever I am tagged as a reviewer on any PR. It tests the changes thoroughly (frontend and backend) and performs security analysis, then creates a detailed review message for updates. It can use skills configured for the corresponding repo or generally available skills. Docs for each codebase live in a .specs repo and are used as review context. It supports selecting the model (opencode free models, opencode GO subscription, Google One AI Pro) before a review runs."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Auto-review on my PRs (Priority: P1)

Whenever I open a PR (or mark a draft ready for review) on any managed repo, the agent clones the repo, loads the relevant docs, runs the security analysis (secrets + LLM review) and PR scope/test-compliance validation, and posts a detailed formal GitHub review (summary + inline comments) using the configured default model. Reviews are gated on CI: they run only after gating CI completes green (or no CI is configured); a failing CI produces a root-cause diagnosis comment instead.

**Why this priority**: This is the core value — a continuously-running reviewer that needs zero manual invocation.

**Independent Test**: Open a PR from my account on a managed repo with green CI; verify a formal review with summary and inline comments is posted, containing security results, scope/test-compliance findings, and the model used.

**Acceptance Scenarios**:

1. **Given** I open a PR on a managed repo, **When** the webhook event is received and gating CI completes green, **Then** a review is posted containing a summary, security results, scope/test-compliance findings, and inline comments.
2. **Given** the PR has no docs folder under `specs/<owner>/<repo>/`, **When** the review runs, **Then** the review still completes and notes that no docs were available.
3. **Given** the PR head SHA is unchanged, **When** a duplicate webhook event arrives, **Then** no duplicate review is posted.

---

### User Story 2 - Review when I am tagged as reviewer (Priority: P1)

When I am added as a requested reviewer on any PR (in any repo the agent can see), the agent runs the same review pipeline and posts its review.

**Why this priority**: Being tagged as reviewer is the second explicit trigger the user asked for; it must behave identically to the first.

**Independent Test**: Request review from my account on a PR; verify a review is posted with the same content contract as the author-triggered review.

**Acceptance Scenarios**:

1. **Given** a reviewer request targets my account, **When** the `review_requested` event arrives, **Then** a review is posted for that PR.
2. **Given** the same PR was already reviewed at the current head, **When** another `review_requested` event arrives, **Then** no second review is posted.

---

### User Story 3 - Per-review model selection (Priority: P2)

I can choose the model for a review per PR by commenting `@review --model <alias>` (aliases defined in config: `free`, `go`; `gemini` is defined but disabled). If no override is given, the configured default model is used.

**requirements updates**
1. here I want to define the model once in the application layer and then this should be customizable as sometimes credits may be finished so I may want to switch between models.

**Why this priority**: The user explicitly wants model selection; it is important but not required for the first review to work.

**Independent Test**: Comment `@review --model go` on a PR and verify the review was generated with the `go` provider (opencode-go) and states which model ran.

**Acceptance Scenarios**:

1. **Given** a configured model alias exists, **When** I comment `@review --model <alias>`, **Then** the review runs with that provider and the review states which model was used.
2. **Given** no override comment exists, **When** a review is triggered, **Then** the configured default model is used.
3. **Given** an unknown model alias is requested, **When** the comment is parsed, **Then** the agent replies with an error listing valid aliases and does not run.

---

### User Story 4 - Minimal PR Review Skills & Repo Conventions (Priority: P2)

The agent uses a self-contained, minimal skill set defined in `agent_skill_set` (including `/code-review` as base review, `/diagnosing-bugs` for root-cause analysis, and `/resolving-merge-conflicts` for conflict guidance) plus repo-scoped rules in `.opencode/` and `AGENTS.md` and docs from this repo's `specs/<owner>/<repo>/` tree, eliminating external global skill mounts. The skills are vendored into the repo under `.agents/skills/` so the container image is self-contained.

**requirements updates**
Defined specific minimal skills for this agent as a base for reviewing changes:
1. `/resolving-merge-conflicts` - Guidance for spotting and resolving merge conflicts.
2. `/diagnosing-bugs` - In-depth root-cause analysis and fix recommendations for detected issues or CI/CD failures.
3. `/code-review` - Base code review standards and structure.

**Why this priority**: Focuses the agent purely on PR reviewing while leveraging repo-specific conventions without external mount complexity.

**Independent Test**: Create a repo with a custom skill and AGENTS.md, plus a docs folder under `specs/<owner>/<repo>/`; verify the review reflects the repo's conventions and uses the minimal skill set.

**Acceptance Scenarios**:

1. **Given** a repo has a custom skill and AGENTS.md, **When** the review runs via the opencode CLI subprocess, **Then** the repo's skills and minimal agent skills are available.
2. **Given** a docs folder exists for the repo under `specs/<owner>/<repo>/`, **When** the review runs, **Then** the review cites the docs for context.
3. **Given** no docs folder exists for the repo, **When** the review runs, **Then** the review proceeds without docs and records the degradation.

---

### User Story 5 - Re-review on new commits (Priority: P2)

When new commits are pushed to a reviewed PR, the agent re-reviews the new head and posts a new review.

**Why this priority**: Keeps the review accurate as the PR evolves; cheap to add given the dedup state.

**Independent Test**: Push a new commit to a reviewed PR; verify a new review is posted for the new head SHA.

**Acceptance Scenarios**:

1. **Given** a PR was reviewed at SHA-A, **When** a `synchronize` event reports SHA-B, **Then** a new review is posted for SHA-B.
2. **Given** a re-review at SHA-B is in progress, **When** another `synchronize` event arrives for the same SHA-B, **Then** the second event is coalesced (no duplicate work).

---

### User Story 6 - Advisory verdicts, CI/CD failure debugging & Scope validation (Priority: P3)

The review is posted with event `COMMENT` (verdict prose lives in the summary — never a formal `APPROVE`). Reviews run only on **green heads**: when gating CI completes with a failure, the agent fetches failure logs, performs root-cause debugging analysis, reports actionable fixes, and posts a **diagnosis comment only** (no review, no security scans). It also validates that only files within the PR scope/issue context are modified and proper tests adhering to repo rules are added.

**Why this priority**: CI/CD runs repo tests automatically; the agent adds value by diagnosing failures and enforcing change scope & test conventions.

**Independent Test**: Trigger a gating CI failure on a PR; verify the agent posts a debugging analysis detailing why CI failed and how to fix it, and that no formal review is posted for that head.

**Acceptance Scenarios**:

1. **Given** a gating CI run fails, **When** `check_run`/`workflow_run` reports `completed` with `failure`, **Then** the agent fetches the failure log via GitHub API and posts a root-cause diagnosis comment (no review, no scans).
2. **Given** a PR modifies files outside the scope of its title/body/issues, **When** the scope check runs on a green head, **Then** the review flags the out-of-scope files.
3. **Given** a PR introduces new code without tests or with tests violating `AGENTS.md` rules, **When** the review runs on a green head, **Then** the review highlights missing/non-compliant test cases.

---

### Edge Cases

- Webhook signature validation fails → reject with 401, log, do not process.
- Webhook arrives for a PR where I am neither author nor requested reviewer → skip, log reason.
- The PAT cannot fetch the PR (permission/scope) → retry, then partial-report.
- No docs folder for the target repo under `specs/<owner>/<repo>/` → review without docs, note in summary.
- CI/CD logs are unavailable or truncated by GitHub API → report CI status with warning on log availability.
- Gating CI exceeds the 60-minute cap → post one "CI hasn't completed; no review run" comment, mark skipped.
- A PR is closed or merged while the review is queued → skip the run, log.
- Two webhooks for the same PR arrive near-simultaneously → SQLite transaction dedups to one review per (repo, PR, head SHA, model).
- A `synchronize` for a new head arrives while the previous head's review is queued/running → new run queues behind the current one (concurrency 1), never dropped.
- The container crashes after posting but before marking `posted` → the idempotency marker on the posted comment prevents any duplicate post.
- Model provider key is missing/invalid → reply to the triggering comment (or log) that the alias is misconfigured; do not run.
- `@review` from an account other than the configured self-account → ignored silently (only self comments are honored).
- Comment command syntax is malformed → reply with usage help.
- Disk usage grows unbounded from persistent clones → LRU eviction by last-used time; configurable cap.
- Tunnel (ngrok) drops → the app queries `localhost:4040/api/tunnels` on restart, re-points registered webhooks to the new public URL; a 5-minute reconcile sweep catches any missed events.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST receive GitHub webhook events (`pull_request` actions `opened`/`ready_for_review`/`synchronize`/`review_requested`, `issue_comment` action `created`, `check_run`/`workflow_run` action `completed`) and MUST verify the `X-Hub-Signature-256` HMAC (shared webhook secret) before processing any payload; all other events are ignored silently (204).
- **FR-002**: System MUST trigger a review for a PR when the configured self-account is the PR author (opened / ready_for_review) or is added as a requested reviewer, or when an `@review` command is commented by the self-account.
- **FR-003**: System MUST review only repos listed in `repo_config` (webhook registration is the allow) and MUST apply a denylist that subtracts within it; skipped PRs are logged with the reason.
- **FR-004**: System MUST deduplicate reviews per (repo, PR number, head SHA, model alias) and re-review when a new head SHA is pushed.
- **FR-005**: System MUST maintain an isolated clone cache inside the container (`workspace_cache_dir`), seeded by plain `git clone` over HTTPS using the PAT, and evicted by LRU against a disk cap.
- **FR-006**: System MUST load per-repo docs from this repo's `specs/<owner>/<repo>/` tree and pass them to the agent as context; a missing folder degrades to review-without-docs.
- **FR-007**: System MUST extract PR intent context from multiple sources (PR title/body, linked GitHub issue details via REST API, commit messages) to perform PR scope validation and flag out-of-scope file modifications.
- **FR-008**: System MUST perform editor-agnostic test compliance validation by checking for matching test additions in the PR diff and inferring testing conventions from existing test patterns in the repository and `CONTRIBUTING.md`. The container NEVER executes the target repo's test suites; "test results" in a review are the CI status plus the compliance findings (MOD-010 is discovery + compliance only).
- **FR-009**: System MUST execute the review agent by spawning an `opencode run` subprocess in the checkout (read-only) with a structured-JSON output contract; no HTTP daemon is used.
- **FR-010**: System MUST gate reviews on CI (Rule B): a run waits for all gating `check_run`/`workflow_run` runs on the head to complete; review and security scans proceed only if none failed. Any gating failure → fetch failure logs via GitHub API and post a root-cause diagnosis comment (no review, no scans).
- **FR-011**: System MUST post a formal GitHub review containing a summary (findings + CI/CD status + scope/test adherence + security results + model used) and inline comments, always with event `COMMENT` and an idempotency marker footer.
- **FR-012**: System MUST post reviews with event `COMMENT` — the advisory verdict (e.g. "looks good", "changes needed") is prose in the summary; formal `APPROVE`/`REQUEST_CHANGES` review events are never used.
- **FR-013**: System MUST support pluggable model providers with aliases (`free` → `opencode`, `go` → `opencode-go`; `gemini` defined but disabled) and automatic credit failover to `switch_default` on 429/402/403 errors with a notice appended to the review.
- **FR-014**: System MUST retry transient failures with backoff (3 attempts, 30s/2min) and post a partial-report comment when a review cannot complete; deterministic outcomes are not retried.
- **FR-015**: System MUST log every run (trigger, inputs, model used, outcome) to structured logs and persist run records.
- **FR-016**: System MUST filter candidate review findings through a deterministic rule-based Validator Filter (diff-line validation, confidence threshold, style blocklist) before posting; a zero-findings result still posts a clean review.

### Key Entities *(include if feature involves data)*

- **Repository**: Target repo (`owner`/`name`), clone path, repo status (managed / denied), docs folder mapping (`specs/<owner>/<repo>/`).
- **PullRequest**: GitHub PR number, head SHA, base branch, author, requested reviewers, state.
- **ReviewRun**: One review attempt: PR reference, head SHA, model alias, status (pending_ci/queued/running/partial/failed/posted/ci-failed/skipped), timestamps, artifact paths.
- **ModelAlias**: Alias → provider + model name + auth reference (e.g. `free`, `go`, `gemini`).
- **CachedRepo**: Persistent clone metadata: owner/name, path, last-used time, size (for LRU eviction).
- **RepoConfig**: Per-repo overrides: managed/enabled, default model alias, denylist override, scope rules override.
- **CIFailureDiagnostic**: CI run ID, job name, failing step, parsed log snippet, root-cause analysis summary, suggested fix.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From gating CI completion to posted review is under 15 minutes for a typical PR; from webhook receipt with no CI configured, under 15 minutes after the settle window.
- **SC-002**: No duplicate review is posted for the same (repo, PR, head SHA, model), verified over 50 webhook events incl. duplicates.
- **SC-003**: At least 95% of green heads post a formal review with summary; the remainder post a partial-report comment (no silent failures).
- **SC-004**: Secrets (PAT, webhook secret, model provider keys) never appear in the repository, logs, or review output — verified by the agent's own gitleaks scan on its own repo.
- **SC-005**: New commits on a reviewed PR produce a new review within 15 minutes of the gating CI completing for the new head.
- **SC-006**: A fresh `docker compose up` on a clean machine reaches "ready, listening for webhooks" with the ngrok tunnel up and registered webhooks pointing at the current public URL.

## Assumptions

- The agent runs as a Docker container on the user's own machine, reachable via an ngrok tunnel (free tier, as a compose sidecar); the GitHub webhook URL points at the tunnel's current public URL and is re-pointed automatically on change.
- The container clones target repos over HTTPS using the PAT; no host projects directory is mounted.
- The GitHub PAT (`GITHUB_TOKEN`, `repo` scope) acts as the configured account for all REST calls and per-repo webhook registration; the agent operates as the self-account only.
- The review skills are self-contained within `agent_skill_set`, vendored into the repo's `.agents/skills/`, without requiring external global skill mounts.
- Docs context comes from this repo's `specs/<owner>/<repo>/` tree.
- OpenCode runs as a one-off CLI subprocess (`opencode run`) inside the Docker container, authenticated via `auth.json` constructed at boot from `.env` tokens (single `OPENCODE_GO_TOKEN`).
- CI/CD workflow runs execute repository test suites automatically on GitHub; the agent never re-runs them locally, and inspects CI status and failure logs via GitHub API.
- Docker images and OpenCode are updated out of band; image build reproducibility is tracked in the repo.
- The constitution at `.specify/memory/constitution.md` is currently the stock template; ratifying a real constitution is tracked as an early task. When ratified, the `specs/` tree serves as the project docs for this feature.
