# verify.ps1 - Run all tests for Guitar-auto-tab (worker DSP + web)
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File verify.ps1
#     -> setup (if needed) + run all tests + build check
#   powershell -ExecutionPolicy Bypass -File verify.ps1 -Cleanup
#     -> same, and if ALL tests pass, delete the legacy tree
#        (app/, frontend/, tests/test_pipeline.py)
#
# Exit code 0 = all green, 1 = something failed (nothing is deleted then).

param([switch]$Cleanup)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$failed = @()

Write-Host "=== 1/5 Python worker: environment ==="
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "venv not found. Creating .venv ..."
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARN] python -m venv failed. Install Python 3.12 first."
        $failed += "venv"
    }
}
if (Test-Path $py) {
    Write-Host "Installing worker dependencies (first run takes a few minutes)..."
    & $py -m pip install -r requirements.txt --quiet --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { $failed += "pip-install" }
}

Write-Host "=== 2/5 Python DSP tests (tests/test_dsp.py) ==="
if (Test-Path $py) {
    & $py tests\test_dsp.py
    if ($LASTEXITCODE -ne 0) { $failed += "test_dsp" }
} else {
    Write-Host "[SKIP] no python available"
    $failed += "test_dsp"
}

Write-Host "=== 3/5 web: install + unit tests (vitest) ==="
$npm = (Get-Command npm -ErrorAction SilentlyContinue)
if (-not $npm) {
    $env:Path = "$env:LOCALAPPDATA\Programs\nodejs;" + $env:Path
    $npm = (Get-Command npm -ErrorAction SilentlyContinue)
}
if ($npm) {
    Set-Location (Join-Path $root "web")
    if (-not (Test-Path "node_modules")) {
        npm install --no-fund --no-audit
        if ($LASTEXITCODE -ne 0) { $failed += "npm-install" }
    }
    npm test
    if ($LASTEXITCODE -ne 0) { $failed += "vitest" }

    Write-Host "=== 4/5 web: typecheck (vue-tsc) ==="
    npm run typecheck
    if ($LASTEXITCODE -ne 0) { $failed += "typecheck" }

    Write-Host "=== 5/5 web: production build ==="
    npm run build
    if ($LASTEXITCODE -ne 0) { $failed += "build" }
    Set-Location $root
} else {
    Write-Host "[SKIP] npm not found. Install Node.js LTS."
    $failed += "npm"
}

Write-Host ""
if ($failed.Count -eq 0) {
    Write-Host "ALL GREEN: dsp tests, vitest, typecheck, build"
    if ($Cleanup) {
        Write-Host "Cleanup: removing legacy app/ frontend/ tests/test_pipeline.py ..."
        Remove-Item -Recurse -Force (Join-Path $root "app")
        Remove-Item -Recurse -Force (Join-Path $root "frontend")
        Remove-Item -Force (Join-Path $root "tests\test_pipeline.py")
        Write-Host "Legacy tree removed. Migration is complete."
    }
    exit 0
} else {
    Write-Host ("FAILED: " + ($failed -join ", "))
    Write-Host "Legacy tree kept. Fix the failures and re-run."
    exit 1
}
