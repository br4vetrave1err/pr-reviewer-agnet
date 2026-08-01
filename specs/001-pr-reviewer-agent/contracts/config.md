# Contract: config.yaml (ARCH-012 Config Loader)

<!-- v-model:traces
  architecture: [ARCH-012]
  modules:      [MOD-016]
  version:      v0.8.0
-->

Source: `v-model/architecture-design.md` §Interface View — ARCH-012. Backed by REQ-IF-004, REQ-016, REQ-017, REQ-CN-001.

## File

`config.yaml` at the repository root, validated against a JSON schema at boot (fail-closed: invalid config → service refuses to start, SCN-IF-004-A2).

## Structure

```yaml
providers:               # model aliases — single app-layer definition (REQ-016)
  free:    { provider: opencode,    model: deepseek-v4-flash-free, enabled: true,  auth_env: OPENCODE_GO_TOKEN }
  go:      { provider: opencode-go, model: deepseek-v4-pro,        enabled: true,  auth_env: OPENCODE_GO_TOKEN }
  gemini:  { provider: google-one,  model: <name>,                 enabled: false, auth_env: OPENCODE_GO_TOKEN }

default_model: free      # active alias — switchable at runtime, no rebuild (REQ-016)
switch_default: go       # alias used on credit-exhaustion fallback (REQ-016)

repo_config:             # source of truth for managed repos (webhook registration = the allow)
  - owner: br4vetrave1err
    repo: developer-roadmap
    default_model: free        # per-repo override (optional)
    enabled: true

denylist: [owner/repo, ...]    # explicit denies — only subtracts within repo_config (REQ-003)

defaults:
  concurrency: 1               # one review at a time (serial execution, REQ-NF-006)
  disk_cap_bytes: <number>
  validator_filter_enabled: true  # deterministic rule-based noise & false-positive filter (REQ-016)

ci_gate:
  enabled: true                # review starts only after gating CI completes green
  settle_seconds: 75           # no-CI bypass window after last webhook for the head
  wait_cap_minutes: 60         # timeout → one "CI hasn't completed" comment, no review

reconcile_interval_seconds: 300   # periodic sweep for missed events (open PRs without a posted review)

retry:
  max_attempts: 3              # initial + 2 retries for transient failures only
  backoff_seconds: [30, 120]   # exponential per attempt (REQ-014)

specs_docs_dir: specs          # docs context: <repo_root>/specs/<owner>/<repo>/ (ARCH-005)
workspace_cache_dir: /var/agent_cache/repos  # isolated agent clone cache (REQ-005)

agent_skill_set:              # defined agent skill set (REQ-017)
  base: /code-review
  situational: [/diagnosing-bugs, /resolving-merge-conflicts]
```

Secrets (`GITHUB_TOKEN`, `WEBHOOK_SECRET`, `OPENCODE_GO_TOKEN`, `NGROK_AUTHTOKEN`) live in a gitignored `.env`, delivered to the container via `env_file`. `auth_env` only names the env var — never the key (REQ-NF-004).

## Accessors (typed, per ARCH-012)

`providers`, `repo_config`, `denylist`, `defaults`, `concurrency`, `disk_cap`, `ci_gate`, `reconcile_interval_seconds`, `retry`, `specs_docs_dir`, `workspace_cache_dir`, `switch_default` (REQ-016), `validator_filter_enabled`, `agent_skill_set` (REQ-017) — plus per-repo overrides from `repo_config` (REQ-003, REQ-008, REQ-012).

## Boot Validation

- `default_model` must reference an enabled alias; otherwise the service **fails to boot** (REQ-016).
- A disabled or missing-key alias (e.g. `gemini`) logs the misconfiguration and is not selectable via `@review --model`; `free`/`go` remain usable (REQ-013).
- An unknown `--model` alias at runtime → reply listing valid aliases, no run (SCN-013-A3).

## Secrets

Key material is **never** in `config.yaml` — only `auth_env` env-var names (REQ-NF-004).

## Verification

ATP-IF-004-A (SCN-IF-004-A1, SCN-IF-004-A2), ATP-016-A, ATP-017-A.
