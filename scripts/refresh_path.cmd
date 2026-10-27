@echo off
REM Refresh PATH in this terminal from Windows registry + WinGet ffmpeg
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYSPATH=%%b"
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USERPATH=%%b"
set "PATH=%SYSPATH%;%USERPATH%"

set "FFMPEG_BIN=%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.1-full_build\bin"
if exist "%FFMPEG_BIN%\ffmpeg.exe" set "PATH=%FFMPEG_BIN%;%PATH%"

echo PATH refreshed for this terminal.
where ffmpeg >nul 2>&1 && (echo OK: ffmpeg found & ffmpeg -version 2>nul | findstr /I "ffmpeg version") || echo WARN: ffmpeg still not found - close terminal and open a new one
