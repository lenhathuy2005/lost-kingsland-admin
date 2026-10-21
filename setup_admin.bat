@echo off
setlocal EnableExtensions
cd /d "%~dp0"
where python >nul 2>nul || (echo Python not found.& pause & exit /b 1)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements-postgres.txt
if errorlevel 1 (pause & exit /b 1)
echo ok>".venv\.deps-v5-installed"
echo Setup complete. Run run_admin.bat next time.
pause
