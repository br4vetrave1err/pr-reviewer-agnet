#!/usr/bin/env bash
# PR Review Agent entrypoint (REQ-NF-004 / REQ-IF-003).
# Builds opencode's auth.json from OPENCODE_GO_TOKEN at boot, then starts the
# app. Fail-closed: missing required secrets refuse to boot.

set -euo pipefail

echo "entrypoint: PR Review Agent boot"

# Required secrets (REQ-NF-004) — fail-closed on the ones that must be present.
: "${GITHUB_TOKEN:?GITHUB_TOKEN is required (REQ-NF-004)}"
: "${WEBHOOK_SECRET:?WEBHOOK_SECRET is required (REQ-NF-004)}"
: "${OPENCODE_GO_TOKEN:?OPENCODE_GO_TOKEN is required (REQ-NF-004)}"

# Build opencode auth.json from the single token source (REQ-IF-003).
AUTH_DIR="${OPENCODE_AUTH_DIR:-$HOME/.config/opencode}"
mkdir -p "$AUTH_DIR"
cat > "$AUTH_DIR/auth.json" <<EOF
{
  "opencode": { "OPENCODE_GO_TOKEN": "$OPENCODE_GO_TOKEN" }
}
EOF
echo "entrypoint: wrote $AUTH_DIR/auth.json"

echo "entrypoint: ready, listening for webhooks"
exec "$@"
