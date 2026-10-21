@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Chua co .venv. Chay run_admin.bat mot lan truoc.
  pause
  exit /b 1
)
echo.
echo LOST KINGSLAND - TEST MEDIA FALLBACK
 echo 1. Dry run
 echo 2. Seed 20 anh
 echo 3. Seed tat ca anh con thieu
 echo 4. Check Bot/Web (Admin phai dang chay)
 echo 5. Thoat
set /p choice=Chon: 
if "%choice%"=="1" ".venv\Scripts\python.exe" seed_test_media_from_web.py
if "%choice%"=="2" ".venv\Scripts\python.exe" seed_test_media_from_web.py --apply --limit 20
if "%choice%"=="3" ".venv\Scripts\python.exe" seed_test_media_from_web.py --apply
if "%choice%"=="4" ".venv\Scripts\python.exe" check_test_media.py
if "%choice%"=="5" exit /b 0
pause
