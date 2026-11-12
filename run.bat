@echo off
rem NOTE: keep this file pure ASCII. cmd.exe parses .bat in the OEM codepage
rem (CP932 on Japanese Windows), so UTF-8 Japanese text here breaks the script.
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto :have_venv
echo [ERROR] .venv not found. See README.md for setup.
pause
exit /b 1

:have_venv
if exist "app\static\dist\index.html" goto :have_ui
echo Frontend not built yet. Building now...
set "PATH=%LOCALAPPDATA%\Programs\nodejs;%PATH%"
where npm >nul 2>nul
if errorlevel 1 goto :no_npm
pushd frontend
call npm install --no-fund --no-audit
if errorlevel 1 goto :npm_fail
call npm run build
if errorlevel 1 goto :build_fail
popd
goto :have_ui

:no_npm
echo [ERROR] UI is not built and npm was not found. See README.md.
pause
exit /b 1

:npm_fail
popd
echo [ERROR] npm install failed.
pause
exit /b 1

:build_fail
popd
echo [ERROR] frontend build failed.
pause
exit /b 1

:have_ui
rem The server opens the browser itself when GAT_OPEN_BROWSER=1 (see app/main.py)
set GAT_OPEN_BROWSER=1
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
