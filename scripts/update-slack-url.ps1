# update-slack-url.ps1
# Run this after each `docker compose up` to sync Slack Event Subscriptions with the new ngrok URL.
# Usage: .\scripts\update-slack-url.ps1

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== PR Review Agent — Slack URL Sync ===" -ForegroundColor Cyan
Write-Host ""

# 1. Get current ngrok URL from the running container's API
Write-Host "Fetching current ngrok tunnel URL..." -ForegroundColor Yellow
try {
    $tunnelsResp = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -Method Get -TimeoutSec 5
    $httpsTunnel = $tunnelsResp.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1
    if (-not $httpsTunnel) {
        throw "No HTTPS tunnel found. Is the app running? (docker compose up -d)"
    }
    $ngrokUrl = $httpsTunnel.public_url.TrimEnd("/")
} catch {
    Write-Host "ERROR: Could not reach ngrok API at http://127.0.0.1:4040" -ForegroundColor Red
    Write-Host "Make sure the stack is running: docker compose up -d" -ForegroundColor Red
    exit 1
}

Write-Host "  Current ngrok URL: $ngrokUrl" -ForegroundColor Green

$slackEventsUrl      = "$ngrokUrl/api/slack/events"
$slackInteractiveUrl = "$ngrokUrl/api/slack/interactivity"

# 2. Verify the endpoints respond correctly
Write-Host ""
Write-Host "Verifying Slack endpoints respond..." -ForegroundColor Yellow
try {
    $verifyBody = '{"type":"url_verification","challenge":"ps1_check"}'
    $verifyResp = Invoke-RestMethod -Uri $slackEventsUrl -Method Post -Body $verifyBody -ContentType "application/json" -TimeoutSec 8
    if ($verifyResp.challenge -eq "ps1_check") {
        Write-Host "  $slackEventsUrl  -> OK (url_verification passed)" -ForegroundColor Green
    } else {
        Write-Host "  WARNING: Unexpected response from events endpoint" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  WARNING: Could not verify events endpoint: $_" -ForegroundColor Yellow
}

# 3. Copy the Slack Events URL to clipboard
Write-Host ""
Write-Host "Copying Events URL to clipboard..." -ForegroundColor Yellow
$slackEventsUrl | Set-Clipboard
Write-Host "  Copied: $slackEventsUrl" -ForegroundColor Green

# 4. Print instructions
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " ACTION REQUIRED — Paste into Slack     " -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Events API Request URL (copied to clipboard):" -ForegroundColor White
Write-Host "  $slackEventsUrl" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Interactivity Request URL:" -ForegroundColor White
Write-Host "  $slackInteractiveUrl" -ForegroundColor Yellow
Write-Host ""

# 5. Open Slack app settings in browser
$appId = "A0BMK4VFFTN"
$slackEventSettingsUrl = "https://api.slack.com/apps/$appId/event-subscriptions"
$slackInteractivityUrl = "https://api.slack.com/apps/$appId/interactive-messages"

Write-Host "Opening Slack Event Subscriptions settings in browser..." -ForegroundColor Yellow
Start-Process $slackEventSettingsUrl

Write-Host ""
Write-Host "Steps to complete in browser:" -ForegroundColor Cyan
Write-Host "  1. Paste the URL (already in clipboard) into 'Request URL'" -ForegroundColor White
Write-Host "  2. Wait for the green Verified checkmark" -ForegroundColor White
Write-Host "  3. Click Save Changes" -ForegroundColor White
Write-Host "  4. Go to Interactivity & Shortcuts and paste: $slackInteractiveUrl" -ForegroundColor White
Write-Host ""
Write-Host "Done! Once saved, @PR-Reviewer review #1 will work in Slack." -ForegroundColor Green
Write-Host ""
