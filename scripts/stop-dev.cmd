@echo off
REM One-click shut-down (reverse order): frontend -> backend -> mysql.
setlocal
cd /d "%~dp0.."

echo.
echo === Attention is all you need - stopping dev stack ===
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\dev.ps1" down all
echo.
pause
if errorlevel 1 exit /b 1
exit /b 0
