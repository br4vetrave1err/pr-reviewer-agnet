# update-slack-url.ps1
# Run after each restart to sync Slack Event Subscriptions with the new ngrok URL.
# Usage: powershell -ExecutionPolicy Bypass -File .\scripts\update-slack-url.ps1

param()

Write-Host "=== PR Review Agent - Slack URL Sync ===" -ForegroundColor Cyan

# 1. Get current ngrok URL
Write-Host "Fetching current ngrok tunnel URL..." -ForegroundColor Yellow
try {
    $tunnelsResp = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 5
    $tunnel = $tunnelsResp.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1
    if (-not $tunnel) {
        throw "No HTTPS tunnel found. Is 'docker compose up -d' running?"
    }
    $ngrokUrl = $tunnel.public_url.TrimEnd("/")
} catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
    exit 1
}

$eventsUrl      = $ngrokUrl + "/api/slack/events"
$interactiveUrl = $ngrokUrl + "/api/slack/interactivity"

Write-Host ("  Tunnel URL: " + $ngrokUrl) -ForegroundColor Green

# 2. Verify the events endpoint
Write-Host "Verifying events endpoint..." -ForegroundColor Yellow
try {
    $body = '{"type":"url_verification","challenge":"ps1_check"}'
    $resp = Invoke-RestMethod -Uri $eventsUrl -Method Post -Body $body -ContentType "application/json" -TimeoutSec 8
    if ($resp.challenge -eq "ps1_check") {
        Write-Host ("  [OK] " + $eventsUrl) -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Unexpected response from events endpoint" -ForegroundColor Yellow
    }
} catch {
    Write-Host ("  [WARN] Could not verify: " + $_) -ForegroundColor Yellow
}

# 3. Copy Events URL to clipboard
$eventsUrl | Set-Clipboard
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " PASTE THESE IN SLACK APP SETTINGS      " -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Events API Request URL (copied to clipboard):" -ForegroundColor White
Write-Host ("  " + $eventsUrl) -ForegroundColor Yellow
Write-Host ""
Write-Host "Interactivity and Shortcuts Request URL:" -ForegroundColor White
Write-Host ("  " + $interactiveUrl) -ForegroundColor Yellow
Write-Host ""

# 4. Open Slack settings in browser
$appId = "A0BMK4VFFTN"
Write-Host "Opening Slack Event Subscriptions settings in browser..." -ForegroundColor Yellow
Start-Process ("https://api.slack.com/apps/" + $appId + "/event-subscriptions")

Write-Host ""
Write-Host "Steps:" -ForegroundColor Cyan
Write-Host "  1. Paste URL (in clipboard) into 'Request URL' field" -ForegroundColor White
Write-Host "  2. Wait for green 'Verified' checkmark" -ForegroundColor White
Write-Host "  3. Click 'Save Changes'" -ForegroundColor White
Write-Host ("  4. Go to Interactivity and Shortcuts, paste: " + $interactiveUrl) -ForegroundColor White
Write-Host "  5. Click 'Save Changes' there too" -ForegroundColor White
Write-Host ""
Write-Host "Done! Then send '@PR-Reviewer review #1' in Slack." -ForegroundColor Green
