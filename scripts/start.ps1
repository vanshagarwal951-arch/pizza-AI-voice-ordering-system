# One-command project startup (Windows)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "=== Voice Ordering System ===" -ForegroundColor Cyan

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}

$env:Path = ".venv\Scripts;" + $env:Path

Write-Host "Installing dependencies..."
pip install -r requirements-dev.txt -q

if (-not (Test-Path ".env")) {
    Copy-Item .env.example .env
    Write-Host "Created .env from template — add API keys for voice mode" -ForegroundColor Yellow
}

Write-Host "Running tests..."
python -m pytest packages/menu_engine/tests -q

Write-Host ""
Write-Host "Starting dashboard at http://localhost:3000" -ForegroundColor Green
Write-Host "Text chat: keyword demo without keys; set GROQ_API_KEY for full AI chat." -ForegroundColor Green
Write-Host "Voice mode:  .\scripts\start_voice.ps1  (checks ffmpeg + API keys)" -ForegroundColor Yellow
Write-Host ""

& "$PSScriptRoot\start_web.ps1"
