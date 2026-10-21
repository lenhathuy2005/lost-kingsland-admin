@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo === Lost Kingsland Admin V27 Studio Diagnostic ===
echo.
echo [Python]
where python
python --version 2>&1
echo.
echo [Project files]
if exist admin_server.py (echo admin_server.py OK) else (echo MISSING admin_server.py)
if exist static\app.js (echo static\app.js OK) else (echo MISSING static\app.js)
if exist data\snapshot.json (echo snapshot OK) else (echo MISSING snapshot)
if exist .env (echo .env exists) else (echo .env MISSING - snapshot mode still works)
echo.
echo [Port 8787]
netstat -ano | findstr ":8787"
echo.
echo [Optional API check if Admin is already running]
powershell -NoProfile -Command "try {(Invoke-RestMethod http://127.0.0.1:8787/api/health -TimeoutSec 2) | ConvertTo-Json -Compress} catch {Write-Host 'Admin API not running yet.'}"
echo.
pause
