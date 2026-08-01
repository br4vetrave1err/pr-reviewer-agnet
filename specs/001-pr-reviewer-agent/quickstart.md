# Quickstart: GitHub PR Review Agent

<!-- v-model:traces
  requirements: [REQ-001, REQ-002, REQ-004, REQ-008, REQ-009, REQ-011, REQ-013, REQ-CN-001]
  system:       [SYS-001, SYS-002, SYS-003, SYS-007, SYS-008, SYS-009, SYS-010]
  architecture: [ARCH-001, ARCH-002, ARCH-003, ARCH-007, ARCH-008, ARCH-009, ARCH-010]
  modules:      [MOD-001, MOD-002, MOD-003, MOD-007, MOD-008, MOD-009, MOD-010]
  version:      v0.8.0
-->

## What this does

A continuously-running Docker compose service (app + `ngrok/ngrok` sidecar) that watches GitHub webhooks for a single configured account. When the account opens a PR, is added as a requested reviewer, or comments `@review`, it gates the review on CI (green heads only), clones the repo, loads docs from this repo's `specs/<owner>/<repo>/` tree, validates PR scope and test compliance (discovery only — it never runs the repo's test suites), runs gitleaks plus the LLM security review, and posts a formal `COMMENT` GitHub review with a summary and inline comments — using a per-PR selectable model from a single app-layer model registry (REQ-016) and a defined agent skill set with `/code-review` at its base (REQ-017).

## Walkthrough 1 — First end-to-end review (P1)

Covers the core flow: webhook → trigger → CI gate → clone → security + compliance → review posted.

1. **Provide secrets via a gitignored `.env`**: `GITHUB_TOKEN` (PAT, `repo` scope), `WEBHOOK_SECRET`, `OPENCODE_GO_TOKEN`, `NGROK_AUTHTOKEN` (never in the repo — REQ-NF-004). The container builds opencode's `auth.json` from `OPENCODE_GO_TOKEN` at boot.
2. **`docker compose up`** on a clean machine reaches "ready, listening for webhooks" with the ngrok tunnel up and registered webhooks re-pointed at the current public URL (REQ-CN-001, SCN-CN-001-A1).
3. Open a PR from your account on a managed repo with gating CI that goes green (REQ-002, SCN-002-A1).
4. The signed webhook is ACKed within 2s (REQ-NF-002, SCN-NF-002-A1); the run enters `pending_ci` and waits for gating CI to complete.
5. Verify the review is posted with a summary containing CI status, security results, scope/test-compliance findings, and the model used (REQ-011, SCN-011-A1), plus inline comments on high-confidence findings (SCN-011-A2).
6. Push a new head — a **new** review posts after CI goes green for it; the identical head+model never double-posts (REQ-004, SCN-004-A1/A2).
7. A missed event (webhook never delivered) is caught by the periodic **reconcile sweep** (`reconcile_interval_seconds`), which re-scans open PR heads lacking a posted marker; the idempotency marker still prevents double-posting (REQ-004, REQ-015).

**Verify with**: ATP-001-A, ATP-002-A, ATP-004-A, ATP-008-A, ATP-009-A, ATP-011-A.

## Walkthrough 1b — Failing CI gets a diagnosis, not a review (P2)

1. Open a PR whose gating CI fails (REQ-010).
2. When `check_run`/`workflow_run` reports `completed` with `failure`, the agent fetches the failure logs and posts a root-cause **diagnosis comment**.
3. No formal review and no security scans are posted for the failed head.
4. A PR with no CI at all is reviewed after the ~75s settle window.

**Verify with**: ATP-010-A.

## Walkthrough 2 — Model selection per PR (P1/P2)

1. Comment `@review --model go` on a PR (REQ-013, SCN-013-A1).
2. The review runs with the `go` provider (opencode-go) and the review states which model was used.
3. With no comment, the configured default model (`free` → opencode) is used (SCN-013-A2).
4. Comment `@review --model nope` or `@review --model gemini` (disabled) → a reply lists valid aliases and no review runs (SCN-013-A3).

**Verify with**: ATP-013-A.

## Walkthrough 4 — Model switching when credits are exhausted (P2)

1. The configured `default_model` provider starts returning 403/429 (credits exhausted).
2. The Model Registry resolves the `switch_default` fallback alias (`go`) and the review completes with the fallback provider (REQ-016, SCN-016-A2).
3. The review states which provider/model actually ran (SCN-016-A3).
4. `@review --model <alias>` on a PR still overrides both defaults for that run, and the registry is unchanged afterwards (SCN-016-A1).

**Verify with**: ATP-016-A.

## Walkthrough 5 — Defined agent skill set (P2)

1. Every review runs with the base `/code-review` skill (REQ-017, SCN-017-A1).
2. When the PR analysis matches a situational context, `/diagnosing-bugs` or `/resolving-merge-conflicts` is added to the review run (SCN-017-A2/A3).
3. A repo that provides no `.opencode/` skill directory still reviews with the base skill set (SCN-017-A4).

**Verify with**: ATP-017-A.

## Walkthrough 3 — Graceful failure and partial report (P1)

1. Trigger a review whose opencode run fails transiently (provider outage, schema violation) (REQ-014, SCN-014-A2).
2. The pipeline retries with exponential backoff (SCN-014-A1; 3 attempts), then posts a partial-report comment stating what ran and what did not.
3. The PR is not hard-blocked; the review stays `COMMENT` (REQ-012, SCN-012-A1).

**Verify with**: ATP-014-A, ATP-012-A.

## Configuration cheat sheet

| Concern | Where | Source |
|---------|-------|--------|
| Model aliases + default | `config.yaml` → `providers`, `default_model`, `switch_default` (REQ-016) | `contracts/config.md` |
| Agent skill set | `config.yaml` → `agent_skill_set` (base `/code-review` + situational, REQ-017) | `contracts/config.md` |
| Managed repos + denylist | `config.yaml` → `repo_config`, `denylist` | REQ-003 |
| CI gate | `config.yaml` → `ci_gate` (enabled, settle window, wait cap) | REQ-010 |
| Concurrency + disk cap | `config.yaml` → `defaults.concurrency` (1), `disk_cap_bytes` | REQ-NF-006, REQ-005 |
| Docs context | `config.yaml` → `specs_docs_dir`; folders keyed `<owner>/<repo>/` | `contracts/specs-repo.md` |
| opencode CLI | `opencode run` subprocess; provider keys via `OPENCODE_GO_TOKEN` | `contracts/opencode-cli.md` |
| Secrets | gitignored `.env` → `env_file` (`GITHUB_TOKEN`, `WEBHOOK_SECRET`, `OPENCODE_GO_TOKEN`, `NGROK_AUTHTOKEN`) | `contracts/config.md` |

## Integration test reference

The end-to-end round-trip (Walkthrough 1) is the integration gate for `/speckit.tasks` and `/speckit.implement` consumption of this plan (`v-model/commands/plan.md` §Round-trip compatibility).
