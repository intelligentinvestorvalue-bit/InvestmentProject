# Stop Cloudflare quick tunnel started by run_tunnel.ps1
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PidFile = Join-Path $Root "data\tunnel.pid"
$UrlFile = Join-Path $Root "data\tunnel_url.txt"

if (-not (Test-Path $PidFile)) {
  Write-Host "No tunnel pid file ($PidFile). Nothing to stop."
  exit 0
}

$pidVal = (Get-Content $PidFile -Raw).Trim()
$proc = Get-Process -Id $pidVal -ErrorAction SilentlyContinue
if ($proc) {
  Stop-Process -Id $pidVal -Force -ErrorAction SilentlyContinue
  Write-Host "Stopped tunnel (pid $pidVal)."
} else {
  Write-Host "Stale pid $pidVal - removing pid file."
}

Remove-Item -Force -ErrorAction SilentlyContinue $PidFile
if ($args -contains "--clear-url") {
  Remove-Item -Force -ErrorAction SilentlyContinue $UrlFile
}
