# Quick Start Guide - Fix Connection Error

## The Problem
You're seeing `ERR_CONNECTION_REFUSED` because the **backend server isn't running**.

**No Supabase needed!** This is a local FastAPI backend.

## Solution: Start the Backend

### Option 1: Quick Script (Recommended)
Open PowerShell in the PDA folder and run:
```powershell
.\START_BACKEND.ps1
```

### Option 2: Manual Start
Open a **new PowerShell terminal** and run:

```powershell
# Navigate to PDA folder
cd C:\Users\holme\Documents\PDA

# Activate virtual environment
.venv\Scripts\Activate.ps1

# Start backend
cd backend
uvicorn main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

### Option 3: Start Both Frontend + Backend Together
```powershell
.\run_dev.ps1
```

## Verify It's Working

1. **Backend running?** Open http://localhost:8000/api/health
   - Should show: `{"status":"ok","data_dir":"..."}`

2. **Frontend running?** Open http://localhost:3000
   - Should show the upload form

3. **Try uploading a PDF** - the error should be gone!

## Troubleshooting

**"uvicorn not found"**
```powershell
pip install uvicorn[standard]
```

**"Module not found"**
```powershell
pip install -e .
```

**Port 8000 already in use**
- Change port: `uvicorn main:app --reload --port 8001`
- Update frontend `.env`: `NEXT_PUBLIC_API_URL=http://localhost:8001`

## What You Need Running

✅ **Backend** (Terminal 1): `http://localhost:8000`  
✅ **Frontend** (Terminal 2): `http://localhost:3000`

Both must be running for the app to work!
