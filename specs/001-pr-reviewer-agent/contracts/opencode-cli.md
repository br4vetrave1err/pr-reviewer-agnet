# Contract: OpenCode CLI Workspace Runner (ARCH-006 Workspace Runner)

<!-- v-model:traces
  architecture: [ARCH-006]
  modules:      [MOD-008]
  version:      v0.8.0
-->

Source: `v-model/architecture-design.md` §Interface View — ARCH-006. Backed by REQ-IF-003, REQ-007, REQ-016, REQ-017.

## Invocation

- **Execution Model**: one-off non-interactive subprocess — `opencode run <session prompt>` with `cwd` set to the target repository checkout (read-only enforced, REQ-CN-004). No daemon, no REST session.
- **CLI**: the opencode CLI is npm-installed into the container image; invoked per review, never left running between reviews.
- **Environment**: provider API keys are resolved by the Model Registry (`auth_ref` — an env var name, never key material) and supplied to the subprocess via environment variables. The container entrypoint pre-populates opencode's `auth.json` from the `.env` tokens at boot (single secret source: `OPENCODE_GO_TOKEN`).
- **Model selection**: resolved alias → provider/model, per-PR `@review --model` override or `switch_default` fallback (ARCH-010, REQ-016). Defaults resolve to `opencode/deepseek-v4-flash-free` (`free`) and `opencode-go/deepseek-v4-pro` (`go`).
- **Mode**: batch, blocking with a bounded timeout; the worker runs the subprocess to completion (or the deadline) and collects stdout/stderr.

## Inputs Injected

| Input | Source |
|-------|--------|
| Docs | `<repo_root>/specs/<owner>/<repo>/` docs (ARCH-005) |
| Repo skills | repo `AGENTS.md` + `.opencode/` (REQ-007) |
| Agent skills | vendored into the repo `.agents/skills/` (`/code-review` base, `/diagnosing-bugs`, `/resolving-merge-conflicts`) (REQ-017) |
| Model | resolved alias → provider/model, per-PR `@review --model` override or `switch_default` fallback (ARCH-010, REQ-016) |
| Review context | PR diff, linked issue context, CI status, scope/test-compliance findings, gitleaks report |

## Output Contract

The session prompt instructs opencode to produce a **single JSON document** on its final turn:

```json
{
  "summary": "markdown summary incl. verdict prose, CI status, model used",
  "findings": [
    { "path": "src/foo.py", "line": 42, "severity": "high|medium|low",
      "title": "short title", "detail": "explanation" }
  ]
}
```

| Direction | Name | Type | Format |
|-----------|------|------|--------|
| Output | result | JSON | Structured review findings, inline comments, risk levels; parsed from the CLI's final-turn JSON, validated against the schema |
| Exception | schema-violation | JSON error | Retry once with the validation error fed back as guidance; on second failure → partial-report fallback (REQ-014) |
| Exception | non-zero exit | Exit code | Classified: retryable (provider outage, transient) vs reportable (REQ-014) |
| Exception | timeout | Deadline | Bounded by run timeout; classified retryable then partial-report |

## Verification

ATP-IF-003-A (SCN-IF-003-A1), ATP-007-A, ATP-016-A, ATP-017-A.
