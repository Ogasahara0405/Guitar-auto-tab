@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [エラー] .venv が見つかりません。README.md のセットアップを実行してください。
  pause
  exit /b 1
)

if not exist "app\static\dist\index.html" (
  echo フロントエンドが未ビルドのため、ビルドします...
  set "PATH=%LOCALAPPDATA%\Programs\nodejs;%PATH%"
  where npm >nul 2>nul
  if errorlevel 1 (
    echo [エラー] ビルド済みUIがなく、npm も見つかりません。README.md を参照してください。
    pause
    exit /b 1
  )
  pushd frontend
  call npm install --no-fund --no-audit
  if errorlevel 1 (
    popd
    echo [エラー] npm install に失敗しました。
    pause
    exit /b 1
  )
  call npm run build
  if errorlevel 1 (
    popd
    echo [エラー] フロントエンドのビルドに失敗しました。
    pause
    exit /b 1
  )
  popd
)

rem サーバーが応答してからブラウザを開く（app/main.py が GAT_OPEN_BROWSER=1 のとき実施）
set GAT_OPEN_BROWSER=1
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
