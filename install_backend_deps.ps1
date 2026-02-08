# Install backend dependencies with timeout and verbose output
# Run: .\install_backend_deps.ps1

Write-Host "Installing backend dependencies..." -ForegroundColor Green
Write-Host ""

# Activate venv
if (Test-Path ".venv\Scripts\Activate.ps1") {
    . .venv\Scripts\Activate.ps1
} else {
    Write-Host "Error: Virtual environment not found!" -ForegroundColor Red
    exit 1
}

# Test pip connection first
Write-Host "Testing pip connection..." -ForegroundColor Cyan
python -m pip --version

# Install with verbose output and timeout
Write-Host ""
Write-Host "Installing uvicorn[standard]..." -ForegroundColor Yellow
Write-Host "This may take 1-2 minutes..." -ForegroundColor Yellow
Write-Host ""

# Try installing with timeout (PowerShell doesn't have built-in timeout for pip, but we can try)
$job = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    . .venv\Scripts\Activate.ps1
    python -m pip install uvicorn[standard] --verbose
}

# Wait up to 5 minutes
$job | Wait-Job -Timeout 300

if ($job.State -eq "Running") {
    Write-Host "Installation is taking longer than expected..." -ForegroundColor Yellow
    Write-Host "You can check progress manually by running: pip install uvicorn[standard]" -ForegroundColor Yellow
    Stop-Job $job
    Remove-Job $job
} else {
    $result = Receive-Job $job
    $result
    Remove-Job $job
    
    Write-Host ""
    Write-Host "Installing PDA package..." -ForegroundColor Yellow
    python -m pip install -e . --verbose
}

Write-Host ""
Write-Host "Done! Try starting the backend now:" -ForegroundColor Green
Write-Host "  cd backend" -ForegroundColor Cyan
Write-Host "  python -m uvicorn main:app --reload --port 8000" -ForegroundColor Cyan
