@echo off
echo Starting PDA Backend Server...
echo.

REM Check if venv exists
if not exist ".venv\Scripts\Activate.bat" (
    echo Error: Virtual environment not found!
    echo Please run: python -m venv .venv
    echo Then: .venv\Scripts\Activate.bat
    echo Then: pip install -e .
    pause
    exit /b 1
)

REM Activate venv
echo Activating virtual environment...
call .venv\Scripts\Activate.bat

REM Change to backend directory
cd backend

REM Check if uvicorn is installed
python -m uvicorn --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Installing uvicorn...
    pip install uvicorn[standard]
    if %ERRORLEVEL% NEQ 0 (
        echo Installing all dependencies...
        cd ..
        pip install -e .
        cd backend
    )
)

REM Start server
echo.
echo Starting backend on http://localhost:8000
echo Press Ctrl+C to stop
echo.
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

pause
