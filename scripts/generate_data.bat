@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: generate_data.bat
:: Generates CAN telemetry sample data for both vehicles
:: locally only — no S3 sync, no Athena repair.
:: ============================================================

:: ---------- Configuration -----------------------------------
set REPO_ROOT=%~dp0..
set SCRIPT=%REPO_ROOT%\sample-data\scripts\generate_sample_data.py
set OUTPUT_DIR=%REPO_ROOT%\data

set VEHICLE_1=VEH_001
set VEHICLE_2=VIN_TEST01
set DURATION_MIN=20
set FREQUENCY_HZ=100
:: ------------------------------------------------------------

echo.
echo ============================================================
echo  CAN Telemetry Data Generator (local only)
echo ============================================================
echo  Vehicles  : %VEHICLE_1%, %VEHICLE_2%
echo  Duration  : %DURATION_MIN% min at %FREQUENCY_HZ% Hz
echo  Output    : %OUTPUT_DIR%
echo ============================================================
echo.

:: ---- Step 1: Generate data for VEHICLE_1 -------------------
echo [1/2] Generating data for %VEHICLE_1%...
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
echo [2/2] Generating data for %VEHICLE_2%...
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

echo ============================================================
echo  Done. Data written to:
echo  %OUTPUT_DIR%\decoded\
echo  %OUTPUT_DIR%\raw\
echo ============================================================
echo.
endlocal
