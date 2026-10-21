@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo  LOST KINGSLAND ADMIN - ONE COMMAND PUBLIC SHARE
echo ============================================================
echo.

rem Validate that a secret exists before exposing anything.
if not exist ".env" (
  echo [ERROR] .env not found. Configure the Admin locally first.
  pause
  exit /b 1
)

findstr /R /C:"^ADMIN_TOKEN=.." ".env" >nul
if errorlevel 1 (
  echo [ERROR] ADMIN_TOKEN is empty/missing in .env.
  echo Set a strong ADMIN_TOKEN before public sharing.
  pause
  exit /b 1
)

set "CLOUDFLARED="
for /f "delims=" %%I in ('where cloudflared 2^>nul') do if not defined CLOUDFLARED set "CLOUDFLARED=%%I"
if not defined CLOUDFLARED if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\cloudflared.exe" set "CLOUDFLARED=%LOCALAPPDATA%\Microsoft\WinGet\Links\cloudflared.exe"
if not defined CLOUDFLARED if exist "%ProgramFiles%\cloudflared\cloudflared.exe" set "CLOUDFLARED=%ProgramFiles%\cloudflared\cloudflared.exe"
if not defined CLOUDFLARED if exist "%ProgramFiles(x86)%\cloudflared\cloudflared.exe" set "CLOUDFLARED=%ProgramFiles(x86)%\cloudflared\cloudflared.exe"

if not defined CLOUDFLARED (
  echo [INFO] cloudflared not found. Installing with winget...
  where winget >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] winget not found. Run install_cloudflared.bat after installing App Installer.
    pause
    exit /b 1
  )
  winget install --id Cloudflare.cloudflared --exact --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (
    echo [ERROR] Could not install cloudflared.
    pause
    exit /b 1
  )
  for /f "delims=" %%I in ('where cloudflared 2^>nul') do if not defined CLOUDFLARED set "CLOUDFLARED=%%I"
  if not defined CLOUDFLARED if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\cloudflared.exe" set "CLOUDFLARED=%LOCALAPPDATA%\Microsoft\WinGet\Links\cloudflared.exe"
  if not defined CLOUDFLARED if exist "%ProgramFiles%\cloudflared\cloudflared.exe" set "CLOUDFLARED=%ProgramFiles%\cloudflared\cloudflared.exe"
  if not defined CLOUDFLARED if exist "%ProgramFiles(x86)%\cloudflared\cloudflared.exe" set "CLOUDFLARED=%ProgramFiles(x86)%\cloudflared\cloudflared.exe"
)

if not defined CLOUDFLARED (
  echo [ERROR] cloudflared installed but executable was not found.
  echo Close this terminal, open a new PowerShell, then run .\cloud.bat again.
  pause
  exit /b 1
)

echo [1/2] Starting protected Admin on 127.0.0.1:8788 ...
start "Lost Kingsland Admin PUBLIC" /D "%CD%" cmd /k "call run_admin_public.bat"
timeout /t 4 /nobreak >nul

echo.
echo [2/2] Opening Cloudflare Quick Tunnel...
echo.
echo LOGIN FOR THE PUBLIC LINK:
echo   Username : admin
echo   Password : use the value of ADMIN_TOKEN in your .env
echo.
echo Write actions inside Admin may ask for ADMIN_TOKEN once more.
echo Share ONLY the https://xxxxx.trycloudflare.com URL printed below.
echo Press Ctrl+C here to close the public tunnel.
echo ============================================================
echo.

"%CLOUDFLARED%" tunnel --url http://127.0.0.1:8788

exit /b %errorlevel%
