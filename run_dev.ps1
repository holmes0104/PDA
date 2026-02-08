# Windows PowerShell script to run both backend and frontend
# Usage: .\run_dev.ps1

$ErrorActionPreference = "Stop"

Write-Host "Starting PDA development servers..."
Write-Host ""

# Check if venv is activated
if (-not $env:VIRTUAL_ENV) {
    Write-Host "Activating virtual environment..."
    if (Test-Path ".venv\Scripts\Activate.ps1") {
        . .venv\Scripts\Activate.ps1
    } else {
        Write-Host "Error: Virtual environment not found. Run: python -m venv .venv"
        exit 1
    }
}

# Start backend in background
Write-Host "Starting FastAPI backend on http://localhost:8000"
$backendJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    . .venv\Scripts\Activate.ps1
    cd backend
    python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
}

# Wait a moment for backend to start
Start-Sleep -Seconds 2

# Start frontend
Write-Host "Starting Next.js frontend on http://localhost:3000"
Write-Host ""
Write-Host "Press Ctrl+C to stop both servers"
Write-Host ""

cd frontend
npm run dev

# Cleanup on exit
Stop-Job $backendJob
Remove-Job $backendJob
