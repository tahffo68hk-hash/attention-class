@echo off
REM One-click bring-up: mysql(3307) -> backend(8000) -> frontend(5173), then open the browser.
REM Idempotent: anything already listening is skipped.
setlocal
cd /d "%~dp0.."

REM The project's python / node live under the WorkBuddy managed runtimes.
set "PATH=C:\Users\yang\.workbuddy\binaries\node\versions\22.22.2-6;%PATH%"

echo.
echo === Attention is all you need - starting dev stack ===
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\dev.ps1" up all
if errorlevel 1 goto failed

echo Opening http://127.0.0.1:5173/ ...
start "" "http://127.0.0.1:5173/"
echo.
echo Backend API docs: http://127.0.0.1:8000/docs
echo Login: admin / admin123
echo.
echo Stop everything later with: scripts\stop-dev.cmd
echo.
pause
exit /b 0

:failed
echo.
echo [FAILED] at least one component did not come up.
echo Check logs in: .workbuddy\logs\   (backend.err.log / frontend.err.log)
echo.
pause
exit /b 1
