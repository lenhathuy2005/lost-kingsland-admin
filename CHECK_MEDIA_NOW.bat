@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" check_test_media.py --admin-base-url http://127.0.0.1:8787
) else (
  python check_test_media.py --admin-base-url http://127.0.0.1:8787
)
pause
