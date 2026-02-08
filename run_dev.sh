#!/usr/bin/env bash
# Cross-platform dev script (bash)
# Usage: ./run_dev.sh

set -e

echo "Starting PDA development servers..."
echo ""

# Check if venv is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Activating virtual environment..."
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    elif [ -f ".venv/Scripts/activate" ]; then
        source .venv/Scripts/activate
    else
        echo "Error: Virtual environment not found. Run: python -m venv .venv"
        exit 1
    fi
fi

# Start backend in background
echo "Starting FastAPI backend on http://localhost:8000"
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

# Wait a moment for backend to start
sleep 2

# Start frontend
echo "Starting Next.js frontend on http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop both servers"
echo ""

cd frontend
npm run dev &
FRONTEND_PID=$!

# Wait for user interrupt
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
