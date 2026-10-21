@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo  Lost Kingsland Admin - PUBLIC SAFE MODE
echo  Local origin: http://127.0.0.1:8788
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found in PATH.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/2] Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 goto :fail
)

if not exist ".venv\.deps-v5-installed" (
  echo [2/2] Installing dependencies...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements-postgres.txt
  if errorlevel 1 goto :fail
  echo ok>".venv\.deps-v5-installed"
)

rem IMPORTANT: public tunnel gets its own process and port.
rem Keep origin loopback-only. Cloudflared connects outbound to this port.
set ADMIN_HOST=127.0.0.1
set ADMIN_PORT=8788
set ADMIN_PUBLIC_MODE=true
set ADMIN_PUBLIC_USER=admin
set ADMIN_LOCAL_OWNER_MODE=false
set ADMIN_ALLOW_REMOTE_NO_AUTH=false

echo [SECURE] Public mode ON - HTTP Basic protects ALL pages/APIs.
echo [SECURE] Local Owner OFF - write actions still require ADMIN_TOKEN.
echo.
".venv\Scripts\python.exe" admin_server.py
exit /b %errorlevel%

:fail
echo.
echo [ERROR] Public Admin failed to start.
pause
exit /b 1
