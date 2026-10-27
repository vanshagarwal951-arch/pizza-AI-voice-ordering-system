@echo off
cd /d "%~dp0.."
call .venv\Scripts\activate.bat 2>nul
if not exist .env (
  echo FAIL: No .env file found.
  exit /b 1
)
findstr /R /C:"^DEEPGRAM_API_KEY=." .env >nul
if errorlevel 1 (
  echo FAIL: DEEPGRAM_API_KEY is empty or missing in .env
  echo Get a free key at https://console.deepgram.com
  exit /b 1
)
echo OK: DEEPGRAM_API_KEY is set in .env
exit /b 0
