@echo off
REM One-click stop of the FastAPI backend only (port 8000). mysql / frontend stay up.
setlocal
cd /d "%~dp0.."

echo.
echo === stopping backend (8000) ===
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\dev.ps1" down backend
echo.
pause
if errorlevel 1 exit /b 1
exit /b 0
