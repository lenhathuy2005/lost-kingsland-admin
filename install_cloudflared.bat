@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo Installing Cloudflare Tunnel client (cloudflared)...
where winget >nul 2>nul
if errorlevel 1 (
  echo [ERROR] winget is not available on this Windows installation.
  echo Install cloudflared manually from Cloudflare, then run cloud.bat again.
  pause
  exit /b 1
)

winget install --id Cloudflare.cloudflared --exact --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
  echo [ERROR] cloudflared installation failed.
  pause
  exit /b 1
)

echo.
echo Installed. Close/reopen the terminal if Windows has not refreshed PATH yet.
pause
