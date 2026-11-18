@echo off
rem NOTE: keep this file pure ASCII. cmd.exe parses .bat in the OEM codepage
rem (CP932 on Japanese Windows), so UTF-8 Japanese text here breaks the script.
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto :have_venv
echo [ERROR] .venv not found. See README.md for setup.
pause
exit /b 1

:have_venv
set "PATH=%LOCALAPPDATA%\Programs\nodejs;%PATH%"
where npm >nul 2>nul
if errorlevel 1 goto :no_npm

if exist "web\node_modules" goto :have_deps
echo Installing web dependencies...
pushd web
call npm install --no-fund --no-audit
if errorlevel 1 goto :npm_fail
popd

:have_deps
if exist "web\.output\server\index.mjs" goto :have_ui
echo Building web app...
pushd web
call npm run build
if errorlevel 1 goto :build_fail
popd

:have_ui
rem GAT_ROOT / GAT_PYTHON tell the web server where the repo root and the
rem Python worker live (see web/nuxt.config.ts).
set "GAT_ROOT=%~dp0"
set "GAT_PYTHON=%~dp0.venv\Scripts\python.exe"
set "PORT=8000"
rem Open the browser once the server has booted (short delay).
start "" /b cmd /c "ping -n 4 127.0.0.1 >nul & start http://127.0.0.1:8000"
node web\.output\server\index.mjs
pause
exit /b 0

:no_npm
echo [ERROR] npm was not found. Install Node.js LTS. See README.md.
pause
exit /b 1

:npm_fail
popd
echo [ERROR] npm install failed.
pause
exit /b 1

:build_fail
popd
echo [ERROR] web build failed.
pause
exit /b 1
