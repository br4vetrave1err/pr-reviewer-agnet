# Contract: GitHub Webhook Delivery (ARCH-001 Webhook Server)

<!-- v-model:traces
  architecture: [ARCH-001]
  modules:      [MOD-001]
  version:      v0.8.0
-->

Source: `v-model/architecture-design.md` §Interface View — ARCH-001. Backed by REQ-001, REQ-IF-002, REQ-NF-002.

## Endpoint

`POST /api/webhook` — exposed through the ngrok sidecar tunnel; the registered webhook URL is the current ngrok public URL, re-pointed automatically on startup (self-heal).

## Headers

| Header | Required | Notes |
|--------|----------|-------|
| `X-GitHub-Event` | Yes | `pull_request`, `issue_comment`, `check_run`, `workflow_run` |
| `X-Hub-Signature-256` | Yes | HMAC-SHA256 of the raw body with the webhook secret; **mandatory** — reject on mismatch |

## Supported Events & Actions

| Event | Actions | Handling |
|-------|---------|----------|
| `pull_request` | `opened`, `ready_for_review` | Enqueue author-triggered review |
| `pull_request` | `synchronize` | Enqueue re-review for the new head SHA |
| `pull_request` | `review_requested` | Enqueue reviewer-triggered review (self account only) |
| `pull_request` | `closed`, `merged` | Mark any queued run for that PR skipped |
| `issue_comment` | `created` | Parse `@review --model <alias>` (self account only); otherwise ignore |
| `check_run` / `workflow_run` | `completed` | Drive the CI gate for the affected head |

`pull_request_review` is **not** subscribed. Anything not in the supported set is ignored silently.

## Responses

| Status | Condition |
|--------|-----------|
| `200` | Valid signature, supported actionable event; ACKed within 2s (REQ-NF-002) |
| `204` | Valid signature but event not actionable (e.g. ignored action/event); acknowledged, no processing |
| `401` | Signature missing or invalid; payload discarded, no processing |

## Payload

GitHub webhook JSON (typed/normalized by MOD-001). Normalization preserves `{event, action, owner, repo, pr_number, head_sha, author, requested_reviewers, comment_body, ci_status}` for the Trigger & Command Filter.

## Verification

ATP-001-A (SCN-001-A1, SCN-001-A2), ATP-001-B, ATP-IF-002-A (SCN-IF-002-A1).
