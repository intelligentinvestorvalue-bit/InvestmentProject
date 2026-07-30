# Install keep-alive: at logon + every N minutes ensure FilingDesk API + UI are up.
# Tunnel is skipped by default (-SkipTunnel) so keep-alive succeeds while logged in.
#
# Usage:
#   .\scripts\install_ensure_online.ps1
#   .\scripts\install_ensure_online.ps1 -Minutes 15
#   .\scripts\install_ensure_online.ps1 -Uninstall

param(
  [int]$Minutes = 15,
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

$arg = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$WatchScript`" -SkipTunnel"
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
  -Description "FilingDesk: keep API (:5000) + UI (:5173) up while logged in. Log: data\ensure_online.log" `
  | Out-Null

Write-Host "Installed scheduled task: $TaskName"
Write-Host "  At logon + every $Minutes minutes while logged in."
Write-Host "  Keep-alive only (tunnel skipped). Cursor/IDE does NOT need to be open."
Write-Host "  Log: $Root\data\ensure_online.log"
Write-Host "  Local UI: http://127.0.0.1:5173"
Write-Host ""
Write-Host "Test now:"
Write-Host "  .\scripts\ensure_online.ps1 -SkipTunnel"
Write-Host "Remove later:"
Write-Host "  .\scripts\install_ensure_online.ps1 -Uninstall"
