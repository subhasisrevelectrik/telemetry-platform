@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: generate_and_sync.bat
:: Generates CAN telemetry sample data for both vehicles,
:: syncs decoded files to S3, and repairs Athena partitions.
:: ============================================================

:: ---------- Configuration -----------------------------------
set REPO_ROOT=%~dp0..
set SCRIPT=%REPO_ROOT%\sample-data\scripts\generate_sample_data.py
set OUTPUT_DIR=%REPO_ROOT%\data

set VEHICLE_1=VEH_001
set VEHICLE_2=VIN_TEST01
set DURATION_MIN=20
set FREQUENCY_HZ=100

set S3_BUCKET=telemetry-data-lake-637423367091
set S3_PREFIX=decoded
set ATHENA_DATABASE=telemetry_db
set ATHENA_WORKGROUP=telemetry-workgroup
:: ------------------------------------------------------------

echo.
echo ============================================================
echo  CAN Telemetry Data Pipeline
echo ============================================================
echo  Vehicles  : %VEHICLE_1%, %VEHICLE_2%
echo  Duration  : %DURATION_MIN% min at %FREQUENCY_HZ% Hz
echo  Output    : %OUTPUT_DIR%
echo  S3 bucket : s3://%S3_BUCKET%/%S3_PREFIX%/
echo ============================================================
echo.

:: ---- Step 1: Generate data for VEHICLE_1 -------------------
echo [1/4] Generating data for %VEHICLE_1%...
python "%SCRIPT%" ^
    --vehicle_id %VEHICLE_1% ^
    --duration_min %DURATION_MIN% ^
    --frequency_hz %FREQUENCY_HZ% ^
    --output_dir "%OUTPUT_DIR%"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Data generation failed for %VEHICLE_1%.
    exit /b 1
)
echo.

:: ---- Step 2: Generate data for VEHICLE_2 -------------------
echo [2/4] Generating data for %VEHICLE_2%...
python "%SCRIPT%" ^
    --vehicle_id %VEHICLE_2% ^
    --duration_min %DURATION_MIN% ^
    --frequency_hz %FREQUENCY_HZ% ^
    --output_dir "%OUTPUT_DIR%"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Data generation failed for %VEHICLE_2%.
    exit /b 1
)
echo.

:: ---- Step 3: Sync decoded data to S3 -----------------------
echo [3/4] Syncing decoded data to s3://%S3_BUCKET%/%S3_PREFIX%/...
aws s3 sync "%OUTPUT_DIR%\decoded" "s3://%S3_BUCKET%/%S3_PREFIX%/" ^
    --exclude "*.DS_Store"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: S3 sync failed.
    exit /b 1
)
echo.

:: ---- Step 4: Repair Athena partitions ----------------------
echo [4/4] Running MSCK REPAIR TABLE in Athena...

:: Use a temp file — for /f backticks can't handle multi-line AWS CLI commands
set ATHENA_TMP=%TEMP%\athena_qid.txt
aws athena start-query-execution ^
    --query-string "MSCK REPAIR TABLE decoded" ^
    --query-execution-context Database=%ATHENA_DATABASE% ^
    --work-group %ATHENA_WORKGROUP% ^
    --output text ^
    --query "QueryExecutionId" > "%ATHENA_TMP%" 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to start Athena query:
    type "%ATHENA_TMP%"
    del "%ATHENA_TMP%" >nul 2>&1
    exit /b 1
)
set /p QUERY_ID=<"%ATHENA_TMP%"
del "%ATHENA_TMP%" >nul 2>&1

if "%QUERY_ID%"=="" (
    echo ERROR: Athena returned an empty query ID.
    exit /b 1
)
echo Athena query ID: %QUERY_ID%

:: Poll until the query finishes
set ATHENA_STATE_TMP=%TEMP%\athena_state.txt
:poll
timeout /t 3 /nobreak >nul
aws athena get-query-execution ^
    --query-execution-id %QUERY_ID% ^
    --output text ^
    --query "QueryExecution.Status.State" > "%ATHENA_STATE_TMP%" 2>&1
set /p QUERY_STATE=<"%ATHENA_STATE_TMP%"
del "%ATHENA_STATE_TMP%" >nul 2>&1

if "%QUERY_STATE%"=="RUNNING" goto poll
if "%QUERY_STATE%"=="QUEUED"  goto poll

if "%QUERY_STATE%"=="SUCCEEDED" (
    echo Athena partition repair succeeded.
) else (
    echo ERROR: Athena query ended with state: %QUERY_STATE%
    exit /b 1
)

echo.
echo ============================================================
echo  Done. New data is live on CloudFront.
echo  Dashboard: https://d3ub59umz6yzfo.cloudfront.net
echo ============================================================
echo.
endlocal
