# Quick script to start the backend server
# Run this in PowerShell: .\START_BACKEND.ps1

Write-Host "Starting PDA Backend Server..." -ForegroundColor Green
Write-Host ""

# Check if venv exists
if (-not (Test-Path ".venv\Scripts\Activate.ps1")) {
    Write-Host "Error: Virtual environment not found!" -ForegroundColor Red
    Write-Host "Please run: python -m venv .venv" -ForegroundColor Yellow
    Write-Host "Then: .venv\Scripts\Activate.ps1" -ForegroundColor Yellow
    Write-Host "Then: pip install -e ." -ForegroundColor Yellow
    exit 1
}

# Activate venv
Write-Host "Activating virtual environment..." -ForegroundColor Cyan
. .venv\Scripts\Activate.ps1

# Check if uvicorn is installed
try {
    python -m uvicorn --version 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw }
} catch {
    Write-Host "Installing uvicorn..." -ForegroundColor Yellow
    pip install uvicorn[standard]
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to install uvicorn. Trying pip install -e ." -ForegroundColor Red
        pip install -e .
    }
}

Write-Host ""
Write-Host "Starting backend on http://localhost:8000" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

# Start backend
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
