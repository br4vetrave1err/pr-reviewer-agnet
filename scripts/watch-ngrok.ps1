# watch-ngrok.ps1
# Runs in the background after `docker compose up -d`.
# Polls the ngrok API every 10s; when the tunnel URL changes it auto-updates
# GitHub webhooks (the app does this itself) AND auto-updates the Slack
# Event Subscriptions Request URL via the Slack API.
#
# Usage:
#   .\scripts\watch-ngrok.ps1
#   or non-blocking:
#   Start-Job -ScriptBlock { & ".\scripts\watch-ngrok.ps1" }

param(
    [int]$PollIntervalSeconds = 10,
    [string]$NgrokApiUrl = "http://127.0.0.1:4040/api/tunnels",
    [string]$SlackAppId = "A0BMK4VFFTN"
)

$ErrorActionPreference = "Continue"

# Load .env file for tokens
function Load-DotEnv {
    param([string]$Path = ".\.env")
    if (Test-Path $Path) {
        Get-Content $Path | ForEach-Object {
            if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
                $name = $matches[1].Trim()
                $value = $matches[2].Trim().Trim('"').Trim("'")
                [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
            }
        }
    }
}

Load-DotEnv

$botToken  = [System.Environment]::GetEnvironmentVariable("SLACK_BOT_TOKEN")
$xappToken = [System.Environment]::GetEnvironmentVariable("SLACK_USER_TOKEN")

function Get-NgrokUrl {
    try {
        $resp = Invoke-RestMethod -Uri $NgrokApiUrl -TimeoutSec 5 -ErrorAction Stop
        $tunnel = $resp.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1
        return $tunnel.public_url.TrimEnd("/")
    } catch {
        return $null
    }
}

function Update-SlackEventUrl {
    param([string]$NgrokUrl)

    $eventsUrl      = $NgrokUrl + "/api/slack/events"
    $interactiveUrl = $NgrokUrl + "/api/slack/interactivity"

    # Try updating via Slack API (apps.manifest.update)
    # Requires App Configuration token - attempt with xapp token
    if ($xappToken) {
        try {
            # Export current manifest
            $exportBody = "app_id=$SlackAppId"
            $exportResp = Invoke-RestMethod `
                -Uri "https://slack.com/api/apps.manifest.export" `
                -Method Post `
                -Body $exportBody `
                -ContentType "application/x-www-form-urlencoded" `
                -Headers @{ Authorization = "Bearer $xappToken" } `
                -TimeoutSec 10

            if ($exportResp.ok) {
                $manifest = $exportResp.manifest
                # Update request URLs in settings
                if (-not $manifest.settings) { $manifest | Add-Member -MemberType NoteProperty -Name "settings" -Value @{} }
                if (-not $manifest.settings.event_subscriptions) { $manifest.settings | Add-Member -MemberType NoteProperty -Name "event_subscriptions" -Value @{} }
                $manifest.settings.event_subscriptions.request_url = $eventsUrl
                if (-not $manifest.settings.event_subscriptions.bot_events) {
                    $manifest.settings.event_subscriptions | Add-Member -MemberType NoteProperty -Name "bot_events" -Value @("app_mention")
                }
                if (-not $manifest.settings.interactivity) { $manifest.settings | Add-Member -MemberType NoteProperty -Name "interactivity" -Value @{} }
                $manifest.settings.interactivity.is_enabled = $true
                $manifest.settings.interactivity.request_url = $interactiveUrl

                $manifestJson = $manifest | ConvertTo-Json -Depth 20 -Compress
                $updateBody = "app_id=$SlackAppId&manifest=" + [System.Uri]::EscapeDataString($manifestJson)
                $updateResp = Invoke-RestMethod `
                    -Uri "https://slack.com/api/apps.manifest.update" `
                    -Method Post `
                    -Body $updateBody `
                    -ContentType "application/x-www-form-urlencoded" `
                    -Headers @{ Authorization = "Bearer $xappToken" } `
                    -TimeoutSec 10

                if ($updateResp.ok) {
                    Write-Host ("[" + (Get-Date -Format "HH:mm:ss") + "] [SLACK-AUTO] Slack manifest updated: " + $eventsUrl) -ForegroundColor Green
                    return $true
                }
                Write-Host ("[" + (Get-Date -Format "HH:mm:ss") + "] [SLACK-WARN] Manifest update failed: " + $updateResp.error) -ForegroundColor Yellow
            }
        } catch {
            Write-Host ("[" + (Get-Date -Format "HH:mm:ss") + "] [SLACK-ERR] API call failed: $_") -ForegroundColor Yellow
        }
    }

    # Fallback: send bot message with new URL + open browser
    Write-Host ("[" + (Get-Date -Format "HH:mm:ss") + "] [SLACK-MANUAL] Cannot auto-update manifest. Opening browser...") -ForegroundColor Yellow

    # Notify in Slack channel via bot message
    if ($botToken) {
        $channelId = [System.Environment]::GetEnvironmentVariable("SLACK_CHANNEL_ID")
        if (-not $channelId) { $channelId = "C0BM96HJ3KM" }
        $msgText = ":warning: *ngrok URL changed!* Update Slack Event Subscriptions Request URL to: " + $eventsUrl
        $msgBody = @{
            channel = $channelId
            text    = $msgText
        } | ConvertTo-Json
        try {
            Invoke-RestMethod `
                -Uri "https://slack.com/api/chat.postMessage" `
                -Method Post `
                -Body $msgBody `
                -ContentType "application/json" `
                -Headers @{ Authorization = "Bearer $botToken" } `
                -TimeoutSec 10 | Out-Null
            Write-Host ("[" + (Get-Date -Format "HH:mm:ss") + "] [SLACK-NOTIFY] Posted new URL to Slack channel") -ForegroundColor Cyan
        } catch {}
    }

    # Copy to clipboard and open browser
    $eventsUrl | Set-Clipboard
    Start-Process ("https://api.slack.com/apps/" + $SlackAppId + "/event-subscriptions")
    Write-Host ("[" + (Get-Date -Format "HH:mm:ss") + "] [ACTION] Paste from clipboard into Slack Event Subscriptions Request URL") -ForegroundColor Magenta
    return $false
}

# ── Main watcher loop ──────────────────────────────────────────────────────────
Write-Host "=== ngrok URL Watcher Started ===" -ForegroundColor Cyan
Write-Host ("Polling " + $NgrokApiUrl + " every " + $PollIntervalSeconds + "s") -ForegroundColor Gray
Write-Host "Press Ctrl+C to stop." -ForegroundColor Gray
Write-Host ""

$lastUrl = $null

while ($true) {
    $currentUrl = Get-NgrokUrl

    if ($null -eq $currentUrl) {
        Write-Host ("[" + (Get-Date -Format "HH:mm:ss") + "] [WAIT] ngrok not reachable yet...") -ForegroundColor DarkGray
    }
    elseif ($currentUrl -ne $lastUrl) {
        if ($null -ne $lastUrl) {
            Write-Host ("[" + (Get-Date -Format "HH:mm:ss") + "] [CHANGE] ngrok URL changed: " + $lastUrl + " => " + $currentUrl) -ForegroundColor Yellow
        } else {
            Write-Host ("[" + (Get-Date -Format "HH:mm:ss") + "] [DETECTED] ngrok URL: " + $currentUrl) -ForegroundColor Green
        }
        $lastUrl = $currentUrl
        Update-SlackEventUrl -NgrokUrl $currentUrl
    }

    Start-Sleep -Seconds $PollIntervalSeconds
}
