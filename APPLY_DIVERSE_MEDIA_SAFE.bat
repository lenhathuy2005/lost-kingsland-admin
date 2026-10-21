@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo Lost Kingsland Admin V6.5 - SAFE DIVERSE MEDIA REBUILD
echo Keeps real/admin-uploaded art. Replaces TEST_PLACEHOLDER only.
echo ============================================================
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" rebuild_diverse_placeholders.py
) else (
  python rebuild_diverse_placeholders.py
)
set RC=%ERRORLEVEL%
echo.
if not "%RC%"=="0" (
  echo FAILED with exit code %RC%.
) else (
  echo SUCCESS. Press Ctrl+F5 in Admin and run Check Bot/Web.
)
pause
exit /b %RC%
