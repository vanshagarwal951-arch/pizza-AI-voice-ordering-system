# Start web dashboard - always on port 3000 (kills stale uvicorn + orphan workers)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$Port = if ($env:WEB_PORT) { [int]$env:WEB_PORT } else { 3000 }

function Get-ListenerPids([int]$TargetPort) {
    $listenerPids = @()
    try {
        Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.OwningProcess -gt 0) { $listenerPids += [int]$_.OwningProcess }
        }
    } catch {
        netstat -ano | Select-String "TCP\s+(\S+):$TargetPort\s+\S+\s+LISTENING\s+(\d+)" | ForEach-Object {
            if ($_ -match "LISTENING\s+(\d+)\s*$") {
                $listenerPids += [int]$Matches[1]
            }
        }
    }
    return $listenerPids | Sort-Object -Unique
}

function Get-DashboardPids() {
    $uvicornPids = @()
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.CommandLine -match "uvicorn web\.main:app") {
            $uvicornPids += $_.ProcessId
        }
    }
    $spawnPids = @()
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.CommandLine -match "spawn_main\(parent_pid=(\d+)") {
            $parent = [int]$Matches[1]
            if ($uvicornPids -contains $parent) {
                $spawnPids += $_.ProcessId
            }
        }
    }
    return @($uvicornPids + $spawnPids) | Sort-Object -Unique
}

function Get-OrphanSpawnPids([int[]]$DeadParentPids) {
    $orphans = @()
    if ($DeadParentPids.Count -eq 0) { return $orphans }
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.CommandLine -match "spawn_main\(parent_pid=(\d+)") {
            $parent = [int]$Matches[1]
            if ($DeadParentPids -contains $parent) {
                $orphans += $_.ProcessId
            }
        }
    }
    return $orphans | Sort-Object -Unique
}

function Stop-Pids([int[]]$Pids) {
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        foreach ($listenerPid in ($Pids | Sort-Object -Unique)) {
            if ($listenerPid -le 0) { continue }
            Write-Host "Stopping PID $listenerPid..." -ForegroundColor Yellow
            cmd /c "taskkill /F /PID $listenerPid /T" 2>$null | Out-Null
            Stop-Process -Id $listenerPid -Force -ErrorAction SilentlyContinue
        }
    } finally {
        $ErrorActionPreference = $prevEap
    }
}

function Clear-Port([int]$TargetPort) {
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        $listenerPids = @(Get-ListenerPids -TargetPort $TargetPort)
        $dashboardPids = @(Get-DashboardPids)
        $deadParents = @()
        foreach ($listenerPid in $listenerPids) {
            if (-not (Get-Process -Id $listenerPid -ErrorAction SilentlyContinue)) {
                $deadParents += $listenerPid
            }
        }
        $orphans = @(Get-OrphanSpawnPids -DeadParentPids $deadParents)
        $toKill = @($listenerPids + $dashboardPids + $orphans) | Sort-Object -Unique

        if ($toKill.Count -eq 0 -and (Get-ListenerPids -TargetPort $TargetPort).Count -eq 0) {
            return $true
        }

        if ($attempt -eq 1) {
            Write-Host "Port $TargetPort in use - stopping stale dashboard process(es)..." -ForegroundColor Yellow
        }
        Stop-Pids -Pids $toKill
        Start-Sleep -Seconds 2
    }
    return (Get-ListenerPids -TargetPort $TargetPort).Count -eq 0
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Run scripts\start.ps1 first to create the virtual environment." -ForegroundColor Red
    exit 1
}

if (-not (Clear-Port -TargetPort $Port)) {
    $blockers = @(Get-ListenerPids -TargetPort $Port)
    Write-Host "ERROR: Could not free port $Port." -ForegroundColor Red
    if ($blockers.Count -gt 0) {
        Write-Host "Still listening: PID(s) $($blockers -join ', '). Close that app or run as admin." -ForegroundColor Yellow
    }
    exit 1
}

$env:Path = ".venv\Scripts;" + $env:Path

Write-Host ""
Write-Host ('DIALOG Pizza dashboard: http://localhost:{0}' -f $Port) -ForegroundColor Green
Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

.\.venv\Scripts\python.exe -m uvicorn web.main:app --app-dir apps/web --reload --host 127.0.0.1 --port $Port
