@echo off
setlocal
cd /d "%~dp0"
echo =====================================================
echo LOST KINGSLAND V7.0 - RESOURCE + 80 ORE DEMO ICONS
echo =====================================================
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
%PY% seed_resource_ore_icons.py --apply
if errorlevel 1 (
  echo.
  echo ERROR. Make sure SQL 80_v70_equipment_ore_materials.sql was run first.
  pause
  exit /b 1
)
echo.
echo Done. Open Admin - Resources and Ores.
pause
