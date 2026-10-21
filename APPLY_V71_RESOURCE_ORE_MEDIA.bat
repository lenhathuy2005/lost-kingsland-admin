@echo off
setlocal
cd /d "%~dp0"
echo =====================================================
echo LOST KINGSLAND V7.1 - RESOURCE + 90 ORE DEMO ICONS
echo =====================================================
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
%PY% seed_resource_ore_icons.py --apply
if errorlevel 1 (
  echo.
  echo ERROR. Make sure SQL 00_RUN_THIS_IN_DBEAVER_V71.sql was run first.
  pause
  exit /b 1
)
echo.
echo Done. Open Admin - Resources and Ores.
pause
