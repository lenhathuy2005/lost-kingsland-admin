@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set ADMIN_URL=http://127.0.0.1:8787

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found in PATH.
  echo Install/repair Python 3.13, then reopen PowerShell.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating isolated Admin virtual environment...
  python -m venv .venv
  if errorlevel 1 goto :fail
)

if not exist ".venv\.deps-v5-installed" (
  echo [2/3] Installing Admin dependencies...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements-postgres.txt
  if errorlevel 1 goto :fail
  echo ok>".venv\.deps-v5-installed"
)

echo [3/3] Starting Lost Kingsland Admin V27 Studio...
start "" "%ADMIN_URL%"
".venv\Scripts\python.exe" admin_server.py
exit /b %errorlevel%

:fail
echo.
echo [ERROR] Admin setup failed. Review the messages above.
pause
exit /b 1
