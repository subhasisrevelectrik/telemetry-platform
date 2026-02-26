# PowerShell script to build Lambda layer with API dependencies
# This creates a layer compatible with AWS Lambda Python 3.12 runtime

Write-Host "Building Lambda layer for API dependencies..." -ForegroundColor Green

# Use venv pip if it exists, otherwise use system pip
$pipCmd = "pip"
if (Test-Path "venv\Scripts\pip.exe")
{
    $pipCmd = "venv\Scripts\pip.exe"
    Write-Host "Using pip from venv" -ForegroundColor Cyan
}
elseif (Test-Path ".venv\Scripts\pip.exe")
{
    $pipCmd = ".venv\Scripts\pip.exe"
    Write-Host "Using pip from .venv" -ForegroundColor Cyan
}

# Create layer directory structure
$layerDir = "lambda-layer\python\lib\python3.12\site-packages"
if (Test-Path "lambda-layer")
{
    Remove-Item -Recurse -Force "lambda-layer"
}
New-Item -ItemType Directory -Force -Path $layerDir | Out-Null

# Install dependencies to layer directory
Write-Host "Installing dependencies..." -ForegroundColor Yellow
& $pipCmd install -r requirements.txt -t $layerDir --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12

if ($LASTEXITCODE -ne 0)
{
    Write-Host "ERROR: pip install failed!" -ForegroundColor Red
    exit 1
}

# Check if mangum was installed
$mangumPath = Join-Path $layerDir "mangum"
if (Test-Path $mangumPath)
{
    Write-Host "SUCCESS: mangum installed successfully" -ForegroundColor Green
}
else
{
    Write-Host "ERROR: mangum installation failed!" -ForegroundColor Red
    exit 1
}

# Clean up unnecessary files to reduce layer size
Write-Host "Cleaning up..." -ForegroundColor Yellow
Get-ChildItem -Path $layerDir -Include "*.pyc", "__pycache__", "*.dist-info" -Recurse | Remove-Item -Recurse -Force

Write-Host ""
Write-Host "SUCCESS: Lambda layer built successfully at: lambda-layer/" -ForegroundColor Green
Write-Host "You can now redeploy the CDK stack." -ForegroundColor Cyan
