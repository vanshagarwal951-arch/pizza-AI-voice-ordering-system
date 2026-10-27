# Start LiveKit voice agent (runs prerequisite check first)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "=== DIALOG Pizza Voice Agent ===" -ForegroundColor Cyan

& "$PSScriptRoot\check_prerequisites.ps1"
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Voice agent not started - fix prerequisites above." -ForegroundColor Red
    exit $LASTEXITCODE
}

$env:Path = ".venv\Scripts;" + $env:Path

$dashPort = if ($env:WEB_PORT) { $env:WEB_PORT } else { 3000 }
Write-Host ""
Write-Host "Starting voice agent (LiveKit worker)..." -ForegroundColor Green
Write-Host "Dashboard: http://localhost:$dashPort (run start_web.cmd in another terminal)" -ForegroundColor Yellow
Write-Host "Join room from Live Order tab - agent starts only after Connect Microphone." -ForegroundColor Yellow
Write-Host ""

.\.venv\Scripts\python.exe apps\voice_server\voice_server\agent.py start
