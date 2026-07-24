# Keep FilingDesk (API + UI) online while logged in. Cloudflare tunnel is optional.
#
# Usage:
#   .\scripts\ensure_online.ps1
#   .\scripts\ensure_online.ps1 -SkipTunnel          # app keep-alive only (default for Task Scheduler)
#   .\scripts\ensure_online.ps1 -NotifyAlways
#
# Schedule: .\scripts\install_ensure_online.ps1

param(
  [switch]$NotifyAlways,
  [switch]$SkipTunnel
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$LogDir = Join-Path $Root "data"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$WatchLog = Join-Path $LogDir "ensure_online.log"
$BackendPidFile = Join-Path $LogDir "backend.pid"
$FrontendPidFile = Join-Path $LogDir "frontend.pid"
$UrlFile = Join-Path $LogDir "tunnel_url.txt"
$NotifiedFile = Join-Path $LogDir "tunnel_url_notified.txt"
$BackendOut = Join-Path $LogDir "backend.out.log"
$BackendErr = Join-Path $LogDir "backend.err.log"
$FrontendOut = Join-Path $LogDir "frontend.out.log"
$FrontendErr = Join-Path $LogDir "frontend.err.log"

$ApiPort = 5000
$UiPort = 5173

function Write-EnsureLog([string]$Message) {
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  Add-Content -Path $WatchLog -Value $line -Encoding UTF8
  Write-Host $line
}

function Import-DotEnv {
  $candidates = @(
    (Join-Path $Root "backend\.env"),
    (Join-Path $Root ".env")
  )
  foreach ($envPath in $candidates) {
    if (-not (Test-Path $envPath)) { continue }
    Get-Content $envPath | ForEach-Object {
      $line = $_.Trim()
      if (-not $line -or $line.StartsWith("#")) { return }
      $eq = $line.IndexOf("=")
      if ($eq -lt 1) { return }
      $key = $line.Substring(0, $eq).Trim()
      $val = $line.Substring($eq + 1).Trim()
      if ($val.StartsWith('"') -and $val.EndsWith('"')) { $val = $val.Substring(1, $val.Length - 2) }
      if ($val.StartsWith("'") -and $val.EndsWith("'")) { $val = $val.Substring(1, $val.Length - 2) }
      if (-not [string]::IsNullOrWhiteSpace($key)) {
        Set-Item -Path "Env:$key" -Value $val
      }
    }
  }
}

function Test-UrlOk([string]$Uri) {
  try {
    $r = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 4
    return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500)
  } catch {
    return $false
  }
}

function Test-TunnelAlive {
  $tunnelPidFile = Join-Path $LogDir "tunnel.pid"
  if (-not (Test-Path $tunnelPidFile)) { return $false }
  $tid = (Get-Content $tunnelPidFile -Raw).Trim()
  if (-not $tid) { return $false }
  return [bool](Get-Process -Id $tid -ErrorAction SilentlyContinue)
}

function Stop-PidFile([string]$PidPath, [string]$Label) {
  if (-not (Test-Path $PidPath)) { return }
  $old = (Get-Content $PidPath -Raw).Trim()
  $op = Get-Process -Id $old -ErrorAction SilentlyContinue
  if ($op) {
    Write-EnsureLog "Stopping stale $Label pid $old"
    Stop-Process -Id $old -Force -ErrorAction SilentlyContinue
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object { $_.ParentProcessId -eq [int]$old } |
      ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
  }
  Remove-Item -Force -ErrorAction SilentlyContinue $PidPath
}

function Start-Backend {
  $py = Join-Path $Root "backend\.venv\Scripts\python.exe"
  if (-not (Test-Path $py)) {
    Write-EnsureLog "ERROR: backend venv missing - create backend\.venv and install requirements"
    return $false
  }

  Stop-PidFile $BackendPidFile "backend"
  Remove-Item -Force -ErrorAction SilentlyContinue $BackendOut, $BackendErr
  Write-EnsureLog "Starting FilingDesk API on port $ApiPort"

  # Avoid Flask reloader child-process PID confusion
  $proc = Start-Process -FilePath $py `
    -ArgumentList @("run_bg.py") `
    -WorkingDirectory (Join-Path $Root "backend") `
    -RedirectStandardOutput $BackendOut `
    -RedirectStandardError $BackendErr `
    -WindowStyle Hidden `
    -PassThru

  $proc.Id | Set-Content -Path $BackendPidFile -Encoding ascii

  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-UrlOk "http://127.0.0.1:${ApiPort}/api/health") {
      Write-EnsureLog "API healthy (pid $($proc.Id))"
      return $true
    }
    if (-not (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) {
      Write-EnsureLog "ERROR: API exited early - see data\backend.err.log"
      return $false
    }
  }
  Write-EnsureLog "ERROR: API did not become healthy in time"
  return $false
}

function Start-Frontend {
  $npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue)
  if (-not $npm) { $npm = Get-Command npm -ErrorAction SilentlyContinue }
  if (-not $npm) {
    Write-EnsureLog "ERROR: npm not found"
    return $false
  }
  if (-not (Test-Path (Join-Path $Root "frontend\node_modules"))) {
    Write-EnsureLog "ERROR: frontend\node_modules missing - run npm install in frontend"
    return $false
  }

  Stop-PidFile $FrontendPidFile "frontend"
  Remove-Item -Force -ErrorAction SilentlyContinue $FrontendOut, $FrontendErr
  Write-EnsureLog "Starting FilingDesk UI on port $UiPort"

  $proc = Start-Process -FilePath $npm.Source `
    -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "$UiPort") `
    -WorkingDirectory (Join-Path $Root "frontend") `
    -RedirectStandardOutput $FrontendOut `
    -RedirectStandardError $FrontendErr `
    -WindowStyle Hidden `
    -PassThru

  $proc.Id | Set-Content -Path $FrontendPidFile -Encoding ascii

  for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-UrlOk "http://127.0.0.1:${UiPort}/") {
      Write-EnsureLog "UI healthy (pid $($proc.Id))"
      return $true
    }
    if (-not (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) {
      Write-EnsureLog "ERROR: UI exited early - see data\frontend.err.log"
      return $false
    }
  }
  Write-EnsureLog "ERROR: UI did not become healthy in time"
  return $false
}

function Send-Ntfy([string]$Url) {
  $topic = $env:NTFY_TOPIC
  if ([string]::IsNullOrWhiteSpace($topic)) {
    Write-EnsureLog "SKIP notify: set NTFY_TOPIC in backend\.env (see CLOUDFLARE_TUNNEL.md)"
    return
  }

  $server = $env:NTFY_SERVER
  if ([string]::IsNullOrWhiteSpace($server)) { $server = "https://ntfy.sh" }
  $server = $server.TrimEnd("/")
  $endpoint = "$server/$topic"

  $headers = @{
    Title = "FilingDesk remote URL"
    Click = $Url
    Priority = "default"
    Tags = "chart_with_upwards_trend,link"
  }
  if (-not [string]::IsNullOrWhiteSpace($env:NTFY_TOKEN)) {
    $headers["Authorization"] = "Bearer $($env:NTFY_TOKEN)"
  }

  $body = "Open FilingDesk:`n$Url`n`n(Works from cellular or any Wi-Fi - laptop must stay on.)"
  try {
    Invoke-RestMethod -Method Post -Uri $endpoint -Body $body -Headers $headers -ContentType "text/plain; charset=utf-8" | Out-Null
    Write-EnsureLog "ntfy sent to topic (server $server)"
    $Url | Set-Content -Path $NotifiedFile -Encoding ascii
  } catch {
    Write-EnsureLog ("ERROR ntfy: {0}" -f $_.Exception.Message)
  }
}

Import-DotEnv

# Prefer -SkipTunnel, else .env ENSURE_SKIP_TUNNEL=1|true|yes (default: skip tunnel for keep-alive)
if (-not $SkipTunnel) {
  $skipEnv = ($env:ENSURE_SKIP_TUNNEL -as [string])
  if ([string]::IsNullOrWhiteSpace($skipEnv) -or ($skipEnv -match '^(1|true|yes)$')) {
    $SkipTunnel = $true
  }
}

Write-EnsureLog "ensure_online check (api $ApiPort / ui $UiPort; skip_tunnel=$SkipTunnel)"

$apiOk = $false
$uiOk = $false

if (Test-UrlOk "http://127.0.0.1:${ApiPort}/api/health") {
  Write-EnsureLog "API OK"
  $apiOk = $true
} else {
  Write-EnsureLog "API down - starting"
  if (Start-Backend) {
    $apiOk = $true
  } else {
    Write-EnsureLog "ABORT: could not start API"
    exit 1
  }
}

if (Test-UrlOk "http://127.0.0.1:${UiPort}/") {
  Write-EnsureLog "UI OK"
  $uiOk = $true
} else {
  Write-EnsureLog "UI down - starting"
  if (Start-Frontend) {
    $uiOk = $true
  } else {
    Write-EnsureLog "ABORT: could not start UI"
    exit 1
  }
}

if ($SkipTunnel) {
  Write-EnsureLog "Tunnel skipped (app keep-alive only). Local UI: http://127.0.0.1:${UiPort}"
  if ($apiOk -and $uiOk) { exit 0 }
  exit 1
}

# Tunnel is best-effort: never fail the job if local apps are healthy.
if ((Test-TunnelAlive) -and (Test-Path $UrlFile)) {
  Write-EnsureLog ("Tunnel OK: {0}" -f (Get-Content $UrlFile -Raw).Trim())
} else {
  Write-EnsureLog "Tunnel down or missing URL - starting (best-effort)"
  & "$Root\scripts\run_tunnel.ps1"
  if ($LASTEXITCODE -ne 0) {
    Write-EnsureLog "WARN: tunnel failed (exit $LASTEXITCODE) - local apps remain up"
    if ($apiOk -and $uiOk) { exit 0 }
    exit 1
  }
}

if (-not (Test-Path $UrlFile)) {
  Write-EnsureLog "WARN: no tunnel URL file yet - local apps remain up"
  exit 0
}

$url = (Get-Content $UrlFile -Raw).Trim()
if (-not $url) {
  Write-EnsureLog "WARN: empty tunnel URL - local apps remain up"
  exit 0
}

$prev = ""
if (Test-Path $NotifiedFile) {
  $prev = (Get-Content $NotifiedFile -Raw).Trim()
}

if ($NotifyAlways -or ($url -ne $prev)) {
  Write-EnsureLog "URL new or NotifyAlways - notifying"
  Send-Ntfy $url
} else {
  Write-EnsureLog "URL unchanged - no push"
}

exit 0
