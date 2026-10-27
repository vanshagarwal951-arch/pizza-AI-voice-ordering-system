@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0.."

set "FFMPEG_BIN="
for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*") do (
  for /d %%B in ("%%D\*full_build\bin") do (
    if exist "%%B\ffmpeg.exe" set "FFMPEG_BIN=%%B"
  )
)
if defined FFMPEG_BIN (
  set "PATH=!FFMPEG_BIN!;%PATH%"
  echo OK: ffmpeg is installed
  "!FFMPEG_BIN!\ffmpeg.exe" -version 2>nul | findstr /I "ffmpeg version"
  exit /b 0
)

echo FAIL: ffmpeg not found. Run: winget install Gyan.FFmpeg
exit /b 1
