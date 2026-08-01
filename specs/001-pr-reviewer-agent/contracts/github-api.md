# Contract: GitHub REST API (ARCH-009 GitHub API Client)

<!-- v-model:traces
  architecture: [ARCH-009]
  modules:      [MOD-013]
  version:      v0.8.0
-->

Source: `v-model/architecture-design.md` §Interface View — ARCH-009. Backed by REQ-IF-001, REQ-NF-003.

## Scope (Personal Access Token)

All calls authenticate as the configured GitHub account via a **classic PAT** supplied in `.env` (`GITHUB_TOKEN`). The PAT requires `repo` scope. The agent acts **only as the configured self-account**; no App installation tokens, no other identities.

| Operation | Endpoint | Notes |
|-----------|----------|-------|
| Read PR | `GET /repos/{owner}/{repo}/pulls/{pr}` | `repo` scope |
| Read PR diff | `GET /repos/{owner}/{repo}/pulls/{pr}` with `Accept: application/vnd.github.diff` | `repo` scope |
| List PR files | `GET /repos/{owner}/{repo}/pulls/{pr}/files` | `repo` scope |
| Get linked issue | `GET /repos/{owner}/{repo}/issues/{issue_number}` | `repo` scope |
| List Check Runs | `GET /repos/{owner}/{repo}/commits/{ref}/check-runs` | `repo` scope |
| List Workflow Runs | `GET /repos/{owner}/{repo}/actions/runs` | `repo` scope |
| Fetch CI Job Log | `GET /repos/{owner}/{repo}/actions/jobs/{job_id}/logs` | `repo` scope |
| Create issue comment | `POST /repos/{owner}/{repo}/issues/{pr}/comments` | `repo` scope |
| Submit review | `POST /repos/{owner}/{repo}/pulls/{pr}/reviews` | `repo` scope |
| List repo webhooks | `GET /repos/{owner}/{repo}/hooks` | Webhook registration/self-heal (setup-time via `gh api`; runtime re-point via httpx) |
| Update repo webhook | `PATCH /repos/{owner}/{repo}/hooks/{id}` | Runtime self-heal after ngrok URL change |

## Request Contract

```
submitReview(owner, repo, pr, head, payload)
payload = {
  commit_id: head,            // must equal PR head SHA
  body: string,               // review summary + "Reviewed by PR Review Agent · run <run_id>" marker
  event: "COMMENT",           // ALWAYS — verdict is prose in the body; never APPROVE/REQUEST_CHANGES
  comments: [{ path, line, side, body }]   // inline comments snapped to diff lines
}
```

Terminal comments (reviews, diagnosis comments, partial reports) carry the idempotency marker `_Reviewed by PR Review Agent · run <run_id>_` as the footer (REQ-NF-005).

## Response Contract

| Direction | Name | Type | Format |
|-----------|------|------|--------|
| Output | reviewId | Number | Posted review id |
| Exception | 403/429 | Retry | Exponential backoff with jitter (REQ-NF-003) |
| Exception | 404 | Skip | PR/resource gone; run marked skipped, no post |

## Verification

ATP-IF-001-A (SCN-IF-001-A1), ATP-NF-003-A (SCN-NF-003-A1).
