# Check voice-mode prerequisites (API keys + ffmpeg)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$env:Path = ".venv\Scripts;" + $env:Path
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Run scripts/start.ps1 first to create the virtual environment." -ForegroundColor Red
    exit 1
}

if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim().Trim('"')
            if ($value) { Set-Item -Path "env:$name" -Value $value }
        }
    }
}

python -m menu_engine.utils.prerequisites
exit $LASTEXITCODE
