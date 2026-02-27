@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: deploy_backend.bat
:: Packages the FastAPI backend source and updates the Lambda
:: function code directly (no CDK deploy needed).
:: ============================================================

:: ---------- Configuration -----------------------------------
set REPO_ROOT=%~dp0..
set BACKEND_DIR=%REPO_ROOT%\backend
set LAMBDA_NAME=TelemetryStack-ApiFunctionCE271BD4-RBGPnWPVQhnT
set ZIP_FILE=%TEMP%\telemetry_backend.zip
:: ------------------------------------------------------------

echo.
echo ============================================================
echo  Backend Deploy Pipeline
echo ============================================================
echo  Source   : %BACKEND_DIR%
echo  Function : %LAMBDA_NAME%
echo ============================================================
echo.

:: ---- Step 1: Build zip -------------------------------------
echo [1/2] Building deployment package...
if exist "%ZIP_FILE%" del "%ZIP_FILE%"

:: Use Python's zipfile module to avoid relying on 7-Zip / tar
python -c "
import zipfile, os, sys

backend = sys.argv[1]
out = sys.argv[2]

EXCLUDE_DIRS = {'venv', '.venv', '__pycache__', 'lambda-layer',
                '.git', 'tests', '.pytest_cache', '.ruff_cache',
                'can_telemetry_backend.egg-info', 'handlers'}

# Never bundle local dev env files — Lambda reads settings from env vars
EXCLUDE_FILES = {'.env'}

with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(backend):
        # Prune excluded directories in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.endswith('.egg-info')]
        for fname in files:
            if fname.endswith(('.pyc', '.pyo')):
                continue
            if fname in EXCLUDE_FILES:
                continue
            full = os.path.join(root, fname)
            arcname = os.path.relpath(full, backend)
            zf.write(full, arcname)
print('ZIP created:', out)
" "%BACKEND_DIR%" "%ZIP_FILE%"

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to create deployment zip.
    exit /b 1
)
echo.

:: ---- Step 2: Update Lambda function code -------------------
echo [2/2] Updating Lambda function code...
set CF_TMP=%TEMP%\lambda_update.txt
aws lambda update-function-code ^
    --function-name %LAMBDA_NAME% ^
    --zip-file "fileb://%ZIP_FILE%" ^
    --query "CodeSize" ^
    --output text > "%CF_TMP%" 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Lambda update failed:
    type "%CF_TMP%"
    del "%CF_TMP%" >nul 2>&1
    del "%ZIP_FILE%" >nul 2>&1
    exit /b 1
)
set /p CODE_SIZE=<"%CF_TMP%"
del "%CF_TMP%" >nul 2>&1
del "%ZIP_FILE%" >nul 2>&1
echo Lambda updated. Deployed size: %CODE_SIZE% bytes
echo.

echo ============================================================
echo  Done. Lambda is live (cold start may take ~2s on first call).
echo ============================================================
echo.
endlocal
