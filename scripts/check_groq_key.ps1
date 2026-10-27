# Verify Groq API key setup (does not print your key)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Test-Path ".env")) {
    Write-Host "FAIL: No .env file found." -ForegroundColor Red
    Write-Host "Run:  copy .env.example .env" -ForegroundColor Yellow
    exit 1
}

$line = Select-String -Path ".env" -Pattern '^\s*GROQ_API_KEY\s*=\s*(.+)\s*$' | Select-Object -First 1
if (-not $line) {
    Write-Host "FAIL: GROQ_API_KEY not found in .env" -ForegroundColor Red
    exit 1
}

$value = $line.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
if (-not $value) {
    Write-Host "FAIL: GROQ_API_KEY is empty in .env" -ForegroundColor Red
    exit 1
}
if (-not $value.StartsWith("gsk_")) {
    Write-Host "FAIL: Key should start with gsk_" -ForegroundColor Red
    exit 1
}
if ($value.Length -lt 30) {
    Write-Host "FAIL: Key looks too short (truncated?)" -ForegroundColor Red
    exit 1
}

Write-Host "OK: GROQ_API_KEY is set in .env (length $($value.Length), starts with gsk_)" -ForegroundColor Green
Write-Host ""
Write-Host "If chat still fails with 401:" -ForegroundColor Yellow
Write-Host "  1. Regenerate key at https://console.groq.com/keys"
Write-Host "  2. Paste into .env as:  GROQ_API_KEY=gsk_...  (no quotes)"
Write-Host "  3. Restart dashboard completely (Ctrl+C, then start again)"
