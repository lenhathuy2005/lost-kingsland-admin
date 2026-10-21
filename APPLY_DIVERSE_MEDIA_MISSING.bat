@echo off
cd /d %~dp0
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe seed_diverse_media.py --apply
) else (
  python seed_diverse_media.py --apply
)
pause
