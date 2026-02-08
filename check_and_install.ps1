# Quick check and install script
Write-Host "Checking if uvicorn is installed..." -ForegroundColor Cyan

cd C:\Users\holme\Documents\PDA
.venv\Scripts\Activate.ps1

# Check if uvicorn is already installed
python -c "import uvicorn; print('uvicorn is installed:', uvicorn.__version__)" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ uvicorn is already installed!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Starting backend..." -ForegroundColor Green
    cd backend
    python -m uvicorn main:app --reload --port 8000
} else {
    Write-Host "❌ uvicorn not found. Installing..." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Option 1: Install from requirements.txt (recommended)" -ForegroundColor Cyan
    Write-Host "  pip install -r requirements.txt" -ForegroundColor White
    Write-Host ""
    Write-Host "Option 2: Install uvicorn only" -ForegroundColor Cyan
    Write-Host "  pip install uvicorn" -ForegroundColor White
    Write-Host ""
    Write-Host "If pip hangs, try:" -ForegroundColor Yellow
    Write-Host "  pip install uvicorn --timeout 60" -ForegroundColor White
    Write-Host ""
    
    # Try quick install
    Write-Host "Attempting quick install..." -ForegroundColor Yellow
    pip install uvicorn --timeout 30
}
