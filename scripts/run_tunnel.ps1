# Expose FilingDesk UI (http://127.0.0.1:5173) via Cloudflare Quick Tunnel.
# No custom domain. No data sync - laptop must keep running backend + frontend.
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
New-Item -ItemType Directory -Force -Path (Join-Path $Root "data") | Out-Null

$Port = if ($env:FILINGDESK_TUNNEL_PORT) { $env:FILINGDESK_TUNNEL_PORT } else { "5173" }
$UrlFile = Join-Path $Root "data\tunnel_url.txt"
$LogFile = Join-Path $Root "data\tunnel.log"
$PidFile = Join-Path $Root "data\tunnel.pid"
$OutLog = "$LogFile.out"
$ErrLog = "$LogFile.err"

function Resolve-Cloudflared {
  $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }

  $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
              [Environment]::GetEnvironmentVariable('Path', 'User')
  $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }

  $candidates = @(
    "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe",
    "$env:ProgramFiles\cloudflared\cloudflared.exe"
  )
  foreach ($p in $candidates) {
    if (Test-Path $p) { return $p }
  }
  return $null
}

$cloudflaredExe = Resolve-Cloudflared
if (-not $cloudflaredExe) {
  Write-Host "cloudflared not found."
  Write-Host "Install: winget install --id Cloudflare.cloudflared"
  Write-Host "Then close and reopen this terminal (PATH refresh), or Docs: CLOUDFLARE_TUNNEL.md"
  exit 1
}

if (Test-Path $PidFile) {
  $oldPid = (Get-Content $PidFile -Raw).Trim()
  $existing = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
  if ($existing) {
    Write-Host "Tunnel already running (pid $oldPid)."
    if (Test-Path $UrlFile) {
      Write-Host "URL: $((Get-Content $UrlFile -Raw).Trim())"
    }
    Write-Host "Stop with: .\scripts\stop_tunnel.ps1"
    exit 0
  }
}

try {
  Invoke-WebRequest -Uri "http://127.0.0.1:${Port}/" -UseBasicParsing -TimeoutSec 3 | Out-Null
} catch {
  Write-Host "FilingDesk UI does not look up on http://127.0.0.1:${Port}"
  Write-Host "Start keep-alive first: .\scripts\ensure_online.ps1"
  exit 1
}

Remove-Item -Force -ErrorAction SilentlyContinue $UrlFile, $LogFile, $OutLog, $ErrLog

Write-Host "Starting Cloudflare quick tunnel -> http://127.0.0.1:${Port}"
Write-Host "Log: $LogFile"

$proc = Start-Process -FilePath $cloudflaredExe `
  -ArgumentList @("tunnel", "--url", "http://127.0.0.1:${Port}") `
  -RedirectStandardOutput $OutLog `
  -RedirectStandardError $ErrLog `
  -PassThru `
  -WindowStyle Hidden

$proc.Id | Set-Content -Path $PidFile -Encoding ascii

function Merge-TunnelLogs {
  $parts = @()
  if (Test-Path $OutLog) { $parts += Get-Content $OutLog -Raw -ErrorAction SilentlyContinue }
  if (Test-Path $ErrLog) { $parts += Get-Content $ErrLog -Raw -ErrorAction SilentlyContinue }
  $merged = ($parts -join "`n")
  Set-Content -Path $LogFile -Value $merged -Encoding utf8
  return $merged
}

$url = $null
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Milliseconds 500
  $alive = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
  if (-not $alive) {
    Merge-TunnelLogs | Out-Null
    Write-Host "cloudflared exited early. Last log lines:"
    Get-Content $LogFile -Tail 40 -ErrorAction SilentlyContinue
    Remove-Item -Force -ErrorAction SilentlyContinue $PidFile
    exit 1
  }
  $log = Merge-TunnelLogs
  if ($log -match "https://[a-zA-Z0-9-]+\.trycloudflare\.com") {
    $url = $Matches[0]
    break
  }
}

if (-not $url) {
  Write-Host "Tunnel started but URL not detected yet. Check:"
  Write-Host "  Get-Content $LogFile -Wait -Tail 20"
  Write-Host "pid: $($proc.Id)"
  exit 0
}

$url | Set-Content -Path $UrlFile -Encoding ascii
Write-Host ""
Write-Host "Public URL (no custom domain):"
Write-Host "  $url"
Write-Host ""
Write-Host "Saved to: $UrlFile"
Write-Host "Stop with: .\scripts\stop_tunnel.ps1"
Write-Host ""
Write-Host "Notes:"
Write-Host "  - No data is synced to Cloudflare - requests proxy to this laptop."
Write-Host "  - URL usually changes every time you restart the tunnel."
Write-Host "  - Keep FilingDesk + this laptop online while using the link."
