@echo off
REM Frontend deployment script for AWS
REM
REM Before running, set the following environment variable:
REM   set FRONTEND_BUCKET=telemetry-frontend-<your-account-id>
REM The bucket name is shown in CDK stack outputs after `cdk deploy`.

if "%FRONTEND_BUCKET%"=="" (
    echo ERROR: FRONTEND_BUCKET environment variable is not set.
    echo Run: set FRONTEND_BUCKET=^<bucket-name-from-cdk-outputs^>
    exit /b 1
)

echo Building frontend...
call npm run build

if %ERRORLEVEL% NEQ 0 (
    echo Build failed!
    exit /b 1
)

echo.
echo Uploading to S3 bucket: %FRONTEND_BUCKET%
aws s3 sync dist/ s3://%FRONTEND_BUCKET%/ --delete

if %ERRORLEVEL% NEQ 0 (
    echo Upload failed!
    exit /b 1
)

echo.
echo Creating CloudFront invalidation...
for /f %%i in ('aws cloudfront list-distributions --query "DistributionList.Items[?contains(Origins.Items[0].DomainName,'%FRONTEND_BUCKET%')].Id" --output text') do set DIST_ID=%%i

if not "%DIST_ID%"=="" (
    aws cloudfront create-invalidation --distribution-id %DIST_ID% --paths "/*"
) else (
    echo Could not auto-detect CloudFront distribution — invalidate manually if needed.
)

echo.
echo ========================================
echo Deployment complete!
echo Check CDK stack outputs for the CloudFront URL.
echo ========================================
