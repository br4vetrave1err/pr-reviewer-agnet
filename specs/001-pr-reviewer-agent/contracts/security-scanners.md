# Contract: Security Scan Pipeline (ARCH-008 Security & CI Debug Pipeline)

<!-- v-model:traces
  architecture: [ARCH-008]
  modules:      [MOD-011, MOD-012]
  version:      v0.8.0
-->

Source: `v-model/architecture-design.md` §Interface View — ARCH-008. Backed by REQ-009, REQ-CN-002.

## Toolchain (all present in image per REQ-CN-002)

| Phase | Tool | Scope | Output expected |
|-------|------|-------|-----------------|
| Secrets | `gitleaks` | Full checkout | Finding list with severity |
| LLM security review | opencode (inside the single `/code-review`-driven session) | Changed files + gitleaks findings + docs | Security assessment of the diff |

Dependency vulnerability scanning (trivy) and SAST (semgrep) are **out of scope for v1** and not installed in the image; the LLM security review is the primary code-security pass.

## Behavior

- Reports normalized into `{secrets, llm}` with severity per finding.
- A missing tool degrades to a skipped phase + log, **never** aborts the run (ARCH-008 Exception).
- The LLM security review runs **inside the single review session** (`/code-review` base skill), not as a separate model call; gitleaks findings and tool output feed it as input context.
- Security/scope review runs **only on green heads** (CI gate passed). A failed head receives a CI diagnosis comment only — no security scans, no review (REQ-010).

## Verification

ATP-009-A (SCN-009-A1..A4).
