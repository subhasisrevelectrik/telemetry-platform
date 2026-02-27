@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: deploy_frontend.bat
:: Builds the React frontend and deploys it to S3 + CloudFront.
:: ============================================================

:: ---------- Configuration -----------------------------------
set REPO_ROOT=%~dp0..
set FRONTEND_DIR=%REPO_ROOT%\frontend
set S3_BUCKET=telemetry-frontend-637423367091
set CF_DISTRIBUTION_ID=E1C5XUQ43I0ZM3
:: ------------------------------------------------------------

echo.
echo ============================================================
echo  Frontend Deploy Pipeline
echo ============================================================
echo  Source  : %FRONTEND_DIR%
echo  S3      : s3://%S3_BUCKET%
echo  CF dist : %CF_DISTRIBUTION_ID%
echo ============================================================
echo.

:: ---- Step 1: Install dependencies (if node_modules missing) -
if not exist "%FRONTEND_DIR%\node_modules" (
    echo [1/3] Installing dependencies...
    pushd "%FRONTEND_DIR%"
    call npm install
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: npm install failed.
        popd
        exit /b 1
    )
    popd
) else (
    echo [1/3] Dependencies already installed, skipping npm install.
)
echo.

:: ---- Step 2: Build ----------------------------------------
echo [2/3] Building frontend (production)...
pushd "%FRONTEND_DIR%"
call npm run build
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Build failed.
    popd
    exit /b 1
)
popd
echo.

:: ---- Step 3: Sync dist/ to S3 -----------------------------
echo [3/3] Uploading to s3://%S3_BUCKET%...
aws s3 sync "%FRONTEND_DIR%\dist" "s3://%S3_BUCKET%/" ^
    --delete ^
    --cache-control "public,max-age=31536000,immutable" ^
    --exclude "index.html"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: S3 sync of assets failed.
    exit /b 1
)

:: Upload index.html separately with no-cache so browsers always
:: fetch the latest shell even when assets are long-cached.
aws s3 cp "%FRONTEND_DIR%\dist\index.html" "s3://%S3_BUCKET%/index.html" ^
    --cache-control "no-cache,no-store,must-revalidate"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: S3 upload of index.html failed.
    exit /b 1
)
echo.

:: ---- Step 4: Invalidate CloudFront cache ------------------
echo [4/3] Invalidating CloudFront cache...
set CF_TMP=%TEMP%\cf_invalidation.txt
aws cloudfront create-invalidation ^
    --distribution-id %CF_DISTRIBUTION_ID% ^
    --paths "/*" ^
    --output text ^
    --query "Invalidation.Id" > "%CF_TMP%" 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: CloudFront invalidation failed:
    type "%CF_TMP%"
    del "%CF_TMP%" >nul 2>&1
    exit /b 1
)
set /p CF_INV_ID=<"%CF_TMP%"
del "%CF_TMP%" >nul 2>&1
echo CloudFront invalidation ID: %CF_INV_ID%
echo (Propagation takes ~30-60 seconds)
echo.

echo ============================================================
echo  Done. Dashboard: https://d3ub59umz6yzfo.cloudfront.net
echo ============================================================
echo.
endlocal
