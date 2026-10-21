@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo Lost Kingsland Admin V6.5 - FORCE DIVERSE MEDIA
ECHO WARNING: overwrites PRIMARY artwork, including real uploads.
echo ============================================================
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" seed_diverse_media.py --apply --force --actor Viet-DiverseMedia-V65-Force
) else (
  python seed_diverse_media.py --apply --force --actor Viet-DiverseMedia-V65-Force
)
set RC=%ERRORLEVEL%
echo.
if not "%RC%"=="0" (echo FAILED with exit code %RC%.) else (echo SUCCESS.)
pause
exit /b %RC%
