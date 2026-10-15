@echo off
REM Show which of the three components is listening.
setlocal
cd /d "%~dp0.."

powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\dev.ps1" status
echo.
pause
exit /b 0
