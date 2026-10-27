# Verify Deepgram API key is set in .env (does not print your key)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Test-Path ".env")) {
    Write-Host "FAIL: No .env file found." -ForegroundColor Red
    exit 1
}

$line = Select-String -Path ".env" -Pattern '^\s*DEEPGRAM_API_KEY\s*=\s*(.+)\s*$' | Select-Object -First 1
if (-not $line) {
    Write-Host "FAIL: DEEPGRAM_API_KEY not found in .env" -ForegroundColor Red
    exit 1
}

$value = $line.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
if (-not $value) {
    Write-Host "FAIL: DEEPGRAM_API_KEY is empty in .env" -ForegroundColor Red
    Write-Host ""
    Write-Host "Get a free key ($200 credit):" -ForegroundColor Yellow
    Write-Host "  1. https://console.deepgram.com/signup"
    Write-Host "  2. Create API Key"
    Write-Host "  3. Add to .env:  DEEPGRAM_API_KEY=your_key_here"
    exit 1
}

Write-Host "OK: DEEPGRAM_API_KEY is set (length $($value.Length))" -ForegroundColor Green
Write-Host "Model: DEEPGRAM_MODEL=nova-2 (default, good for voice ordering)"
Write-Host ""
Write-Host "Restart voice agent:  .\scripts\start_voice.ps1"
