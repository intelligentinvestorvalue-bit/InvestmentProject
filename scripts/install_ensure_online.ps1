# Install keep-alive: every N minutes ensure FilingDesk + tunnel are up,
# and push a new trycloudflare URL to your phone via ntfy (when it changes).
#
# Usage:
#   .\scripts\install_ensure_online.ps1
#   .\scripts\install_ensure_online.ps1 -Minutes 30
#   .\scripts\install_ensure_online.ps1 -Uninstall

param(
  [int]$Minutes = 30,
  [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$TaskName = "FilingDesk Ensure Online"
$WatchScript = Join-Path $Root "scripts\ensure_online.ps1"

if ($Uninstall) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "Removed scheduled task: $TaskName"
  exit 0
}

if (-not (Test-Path $WatchScript)) {
  Write-Host "Missing $WatchScript"
  exit 1
}
if ($Minutes -lt 2) {
  Write-Host "Minutes must be >= 2"
  exit 1
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$arg = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$WatchScript`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arg -WorkingDirectory $Root

$start = (Get-Date).AddMinutes(1)
$repeat = New-ScheduledTaskTrigger -Once -At $start `
  -RepetitionInterval (New-TimeSpan -Minutes $Minutes) `
  -RepetitionDuration (New-TimeSpan -Days 3650)

$atLogon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
  -WakeToRun:$false

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $action `
  -Trigger @($atLogon, $repeat) `
  -Settings $settings `
  -Principal $principal `
  -Description "FilingDesk: keep API + UI + Cloudflare tunnel up; ntfy push when URL changes. Log: data\ensure_online.log" `
  | Out-Null

Write-Host "Installed scheduled task: $TaskName"
Write-Host "  At logon + every $Minutes minutes while logged in."
Write-Host "  Runs in the background via Task Scheduler - Cursor/IDE does NOT need to be open."
Write-Host "  Log: $Root\data\ensure_online.log"
Write-Host ""
Write-Host "Checklist:"
Write-Host "  - backend\.env has NTFY_TOPIC set (see CLOUDFLARE_TUNNEL.md)"
Write-Host "  - Phone: install ntfy by Philipp C. Heckel and subscribe to that topic"
Write-Host "  - Power: never sleep when plugged in"
Write-Host "  - Test:  .\scripts\ensure_online.ps1"
Write-Host "  - Force: .\scripts\ensure_online.ps1 -NotifyAlways"
Write-Host "Remove later:"
Write-Host "  .\scripts\install_ensure_online.ps1 -Uninstall"
Write-Host ""
Write-Host "Docs: CLOUDFLARE_TUNNEL.md"
