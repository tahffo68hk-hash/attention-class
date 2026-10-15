#Requires -Version 5.1
<#
    Attention is all you need - local dev stack control (IDEMPOTENT)

    Bring-up order : mysql(3307) -> backend(8000) -> frontend(5173)
    Shut-down order: frontend -> backend -> mysql          (exact reverse)

    Safe to run 'up' repeatedly: anything already listening is skipped,
    so you can never end up with two mysqld processes on the same datadir.

    Usage (also wrapped by double-clickable .cmd files in this folder):
      scripts\start-dev.cmd      -> up all, then opens http://127.0.0.1:5173/
      scripts\stop-dev.cmd       -> down all   (frontend -> backend -> mysql)
      scripts\stop-backend.cmd   -> down backend only
      scripts\status-dev.cmd     -> status

      powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 status
      powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 up
      powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 up backend
      powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 restart frontend
      powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 down
      powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 down db

    Graceful mysql shutdown needs the root password. It is taken from
    $env:MYSQL_ROOT_PASSWORD, or from MYSQL_ROOT_PASSWORD in the repo-root .env.
    If neither is available, mysql is force-stopped (InnoDB crash recovery on
    the next start). The password value is never printed.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('status', 'up', 'down', 'restart')]
    [string]$Action = 'status',

    [Parameter(Position = 1)]
    [ValidateSet('all', 'db', 'backend', 'frontend')]
    [string]$Target = 'all'
)

$ErrorActionPreference = 'Stop'

# --------------------------------------------------------------------------
# Machine-specific paths. Edit only this block if your install differs.
# --------------------------------------------------------------------------
$Root        = Split-Path -Parent $PSScriptRoot
$Python      = 'C:\Users\yang\.workbuddy\binaries\python\envs\default\Scripts\python.exe'
$MysqlBin    = 'C:\mysql-8.0.32-winx64\bin'
$DataDir     = Join-Path $Root '.mysql\data'
$BackendDir  = Join-Path $Root 'backend'
$FrontendDir = Join-Path $Root 'frontend'
$LogDir      = Join-Path $Root '.workbuddy\logs'

$Ports = [ordered]@{ db = 3307; backend = 8000; frontend = 5173 }

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

$script:Failed = $false

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
function Get-PidOnPort {
    param([int]$Port)
    $c = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if ($c) { return [int]($c | Select-Object -First 1).OwningProcess }
    return $null
}

function Wait-Port {
    param([int]$Port, [int]$TimeoutSec = 60)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Get-PidOnPort $Port) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Test-BackendHealthy {
    param([int]$TimeoutSec = 40)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Write-Step { param([string]$Text, [string]$Color = 'Gray') Write-Host $Text -ForegroundColor $Color }

# Graceful mysql shutdown needs the root password. Resolution order:
#   1. $env:MYSQL_ROOT_PASSWORD (already set by the caller)
#   2. MYSQL_ROOT_PASSWORD key in the repo-root .env  (the docker-compose interpolation file)
# The value is NEVER echoed -- only the source is reported.
function Resolve-MysqlRootPassword {
    if ($env:MYSQL_ROOT_PASSWORD) { return 'env' }
    $envFile = Join-Path $Root '.env'
    if (-not (Test-Path -LiteralPath $envFile)) { return $null }
    foreach ($line in @(Get-Content -LiteralPath $envFile -ErrorAction SilentlyContinue)) {
        $t = "$line".Trim()
        if (-not $t -or $t.StartsWith('#')) { continue }
        $i = $t.IndexOf('=')
        if ($i -lt 1) { continue }
        if ($t.Substring(0, $i).Trim() -ne 'MYSQL_ROOT_PASSWORD') { continue }
        $v = $t.Substring($i + 1).Trim().Trim([char]34, [char]39)
        if ($v) { $env:MYSQL_ROOT_PASSWORD = $v; return '.env' }
    }
    return $null
}

# Two mysqld processes sharing one datadir is the dangerous case we guard against.
function Find-StrayMysqld {
    $norm = $DataDir.Replace('\', '/').ToLowerInvariant()
    $owner = Get-PidOnPort $Ports.db
    return @(
        Get-CimInstance Win32_Process -Filter "name='mysqld.exe'" -ErrorAction SilentlyContinue |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine.Replace('\', '/').ToLowerInvariant().Contains($norm) -and
                $_.ProcessId -ne $owner
            }
    )
}

# --------------------------------------------------------------------------
# start
# --------------------------------------------------------------------------
function Start-Db {
    $existing = Get-PidOnPort $Ports.db
    if ($existing) { Write-Step "  [skip ] mysql already on 3307 (pid $existing)" 'DarkGray'; return }

    $stray = @(Find-StrayMysqld)
    if ($stray.Count -gt 0) {
        $ids = ($stray | ForEach-Object { $_.ProcessId }) -join ', '
        Write-Step "  [WARN ] another mysqld (pid $ids) already holds this datadir but is not listening." 'Yellow'
        Write-Step "         Starting a second one risks InnoDB damage. Run 'down db' first, or kill: Stop-Process -Id $ids -Force" 'Yellow'
        $script:Failed = $true
        return
    }

    Write-Host '  [start] mysql on 3307 ... ' -NoNewline
    $argLine = "--no-defaults --datadir=`"$DataDir`" --port=$($Ports.db) " +
               "--bind-address=127.0.0.1 --console --log-error-verbosity=2"
    Start-Process -FilePath (Join-Path $MysqlBin 'mysqld.exe') -ArgumentList $argLine -WindowStyle Minimized | Out-Null

    if (Wait-Port $Ports.db 60) {
        Write-Step "ok (pid $(Get-PidOnPort $Ports.db))" 'Green'
        # Self-heal: launching mysqld from a shell background job (e.g. 'mysqld ... &')
        # can leave a twin process that shares this datadir but never binds the port.
        # Two mysqld on one datadir risks InnoDB damage, so remove the twin now that
        # our instance is confirmed listening.
        $twin = @(Find-StrayMysqld)
        foreach ($t in $twin) {
            Write-Step "  [clean] dropped twin mysqld pid $($t.ProcessId) (same datadir, never bound)" 'Yellow'
            Stop-Process -Id $t.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
    else { Write-Step 'TIMEOUT - check the minimized mysqld window' 'Red'; $script:Failed = $true }
}

function Start-Backend {
    $existing = Get-PidOnPort $Ports.backend
    if ($existing) { Write-Step "  [skip ] backend already on 8000 (pid $existing)" 'DarkGray'; return }

    Write-Host '  [start] backend on 8000 ... ' -NoNewline
    Start-Process -FilePath $Python `
        -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$($Ports.backend)") `
        -WorkingDirectory $BackendDir `
        -RedirectStandardOutput (Join-Path $LogDir 'backend.out.log') `
        -RedirectStandardError  (Join-Path $LogDir 'backend.err.log') | Out-Null

    if (Wait-Port $Ports.backend 60) {
        if (Test-BackendHealthy 40) { Write-Step "ok (pid $(Get-PidOnPort $Ports.backend), /health 200)" 'Green' }
        else { Write-Step 'listening but /health did not return 200 - see logs\backend.err.log' 'Yellow'; $script:Failed = $true }
    } else {
        Write-Step 'TIMEOUT - see logs\backend.err.log' 'Red'
        Write-Step '        (a placeholder credential in backend\.env makes the app refuse to start by design)' 'Yellow'
        $script:Failed = $true
    }
}

function Start-Frontend {
    $existing = Get-PidOnPort $Ports.frontend
    if ($existing) { Write-Step "  [skip ] frontend already on 5173 (pid $existing)" 'DarkGray'; return }

    $npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue)
    if (-not $npm) { Write-Step '  [FAIL ] npm.cmd not found in PATH' 'Red'; $script:Failed = $true; return }

    Write-Host '  [start] frontend on 5173 ... ' -NoNewline
    Start-Process -FilePath $npm.Source -ArgumentList @('run', 'dev') `
        -WorkingDirectory $FrontendDir `
        -RedirectStandardOutput (Join-Path $LogDir 'frontend.out.log') `
        -RedirectStandardError  (Join-Path $LogDir 'frontend.err.log') | Out-Null

    if (Wait-Port $Ports.frontend 90) { Write-Step "ok (pid $(Get-PidOnPort $Ports.frontend))" 'Green' }
    else { Write-Step 'TIMEOUT - see logs\frontend.err.log' 'Red'; $script:Failed = $true }
}

# --------------------------------------------------------------------------
# stop
# --------------------------------------------------------------------------
function Stop-Db {
    $p = Get-PidOnPort $Ports.db
    $stray = @(Find-StrayMysqld)
    foreach ($s in $stray) {
        Write-Step "  [stop ] stray mysqld pid $($s.ProcessId) (holds datadir, not listening)" 'Yellow'
        Stop-Process -Id $s.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if (-not $p) { if ($stray.Count -eq 0) { Write-Step '  [skip ] mysql not running' 'DarkGray' }; return }

    $admin = Join-Path $MysqlBin 'mysqladmin.exe'
    $pwSource = Resolve-MysqlRootPassword
    if ($pwSource -and (Test-Path -LiteralPath $admin)) {
        Write-Host "  [stop ] mysql (graceful shutdown, root pw from $pwSource) ... " -NoNewline
        & $admin -h 127.0.0.1 -P $Ports.db -u root "--password=$($env:MYSQL_ROOT_PASSWORD)" shutdown 2>$null | Out-Null
        $deadline = (Get-Date).AddSeconds(30)
        while ((Get-Date) -lt $deadline -and (Get-PidOnPort $Ports.db)) { Start-Sleep -Milliseconds 500 }
        if (-not (Get-PidOnPort $Ports.db)) { Write-Step 'ok' 'Green'; return }
        Write-Step 'did not stop, forcing' 'Yellow'
    } else {
        Write-Step '  [WARN ] MYSQL_ROOT_PASSWORD not set -> force-stopping mysql (InnoDB crash recovery on next start)' 'Yellow'
    }
    Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
    Write-Step '  [stop ] mysql forced' 'Green'
}

# NOTE: not named Stop-Service -- that would shadow the built-in cmdlet.
function Stop-PortProcess {
    param([int]$Port, [string]$Name)
    $p = Get-PidOnPort $Port
    if (-not $p) { Write-Step "  [skip ] $Name not running" 'DarkGray'; return }
    Write-Host "  [stop ] $Name (pid $p) ... " -NoNewline
    Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
    if (Get-PidOnPort $Port) { Write-Step 'still listening' 'Red'; $script:Failed = $true } else { Write-Step 'ok' 'Green' }
}

# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------
function Show-Status {
    Write-Host ''
    Write-Host '  component   port   state' -ForegroundColor White
    Write-Host '  ---------   ----   -----' -ForegroundColor DarkGray
    foreach ($kv in $Ports.GetEnumerator()) {
        $p = Get-PidOnPort $kv.Value
        if ($p) {
            $name = (Get-Process -Id $p -ErrorAction SilentlyContinue).ProcessName
            Write-Host ("  {0,-10}  {1,-4}   UP   pid {2} ({3})" -f $kv.Key, $kv.Value, $p, $name) -ForegroundColor Green
        } else {
            Write-Host ("  {0,-10}  {1,-4}   --   down" -f $kv.Key, $kv.Value) -ForegroundColor DarkGray
        }
    }
    $pwSource = Resolve-MysqlRootPassword
    if ($pwSource) { Write-Host "  mysql shutdown: graceful (root password from $pwSource)" -ForegroundColor DarkGray }
    else { Write-Host '  mysql shutdown: FORCE -- set $env:MYSQL_ROOT_PASSWORD or add it to .env' -ForegroundColor Yellow }

    $stray = @(Find-StrayMysqld)
    if ($stray.Count -gt 0) {
        $ids = ($stray | ForEach-Object { $_.ProcessId }) -join ', '
        Write-Host ''
        Write-Host "  !! STRAY mysqld holding $DataDir but not listening: pid $ids" -ForegroundColor Red
        Write-Host '     This must be cleaned up before the next start. Run: dev.ps1 down db' -ForegroundColor Red
    }
    Write-Host ''
}

# --------------------------------------------------------------------------
# dispatch
# --------------------------------------------------------------------------
$doDb       = ($Target -eq 'all' -or $Target -eq 'db')
$doBackend  = ($Target -eq 'all' -or $Target -eq 'backend')
$doFrontend = ($Target -eq 'all' -or $Target -eq 'frontend')

switch ($Action) {
    'status' { Show-Status }
    'up' {
        Write-Host ''
        if ($doDb)       { Start-Db }
        if ($doBackend)  { Start-Backend }
        if ($doFrontend) { Start-Frontend }
        Write-Host ''
        Show-Status
        if ($doBackend -or $doFrontend) {
            Write-Host '  backend docs : http://127.0.0.1:8000/docs' -ForegroundColor DarkGray
            Write-Host '  frontend     : http://127.0.0.1:5173/' -ForegroundColor DarkGray
            Write-Host '  logs         : .workbuddy\logs\' -ForegroundColor DarkGray
            Write-Host ''
        }
    }
    'down' {
        Write-Host ''
        if ($doFrontend) { Stop-PortProcess $Ports.frontend 'frontend' }
        if ($doBackend)  { Stop-PortProcess $Ports.backend  'backend' }
        if ($doDb)       { Stop-Db }
        Write-Host ''
        Show-Status
    }
    'restart' {
        Write-Host ''
        Write-Step "  restart $Target" 'White'
        # stop in reverse dependency order, then start in forward order
        if ($doFrontend) { Stop-PortProcess $Ports.frontend 'frontend' }
        if ($doBackend)  { Stop-PortProcess $Ports.backend  'backend' }
        if ($doDb)       { Stop-Db }
        Start-Sleep -Milliseconds 800
        if ($doDb)       { Start-Db }
        if ($doBackend)  { Start-Backend }
        if ($doFrontend) { Start-Frontend }
        Write-Host ''
        Show-Status
    }
}

if ($script:Failed) { exit 1 } else { exit 0 }
