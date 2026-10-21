@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".env" (
  copy /Y ".env.example" ".env" >nul
  echo [INFO] Created .env from .env.example. Edit DATABASE_URL password before starting Admin.
)
findstr /B /C:"ADMIN_LOCAL_OWNER_MODE=" .env >nul || echo ADMIN_LOCAL_OWNER_MODE=true>>.env
findstr /B /C:"ADMIN_OWNER_NAME=" .env >nul || echo ADMIN_OWNER_NAME=Viet>>.env
findstr /B /C:"ADMIN_ALLOW_REMOTE_NO_AUTH=" .env >nul || echo ADMIN_ALLOW_REMOTE_NO_AUTH=false>>.env
findstr /B /C:"ADMIN_HOST=" .env >nul || echo ADMIN_HOST=127.0.0.1>>.env
echo.
echo [OK] Local Owner account enabled: Viet / OWNER
echo [OK] No ADMIN_TOKEN prompt on 127.0.0.1.
echo [SAFE] Remote no-auth remains disabled.
echo.
echo Restart Admin with: run_admin.bat
pause
