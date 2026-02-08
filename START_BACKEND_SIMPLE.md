# 🚀 Quick Fix: Start Backend Server

## The Problem
You're seeing `ERR_CONNECTION_REFUSED` because the backend server isn't running.

## Solution: Start the Backend (3 Steps)

### Step 1: Open PowerShell
Open PowerShell in the PDA folder:
- Press `Win + R`
- Type: `powershell`
- Navigate: `cd C:\Users\holme\Documents\PDA`

### Step 2: Activate Virtual Environment
```powershell
.venv\Scripts\Activate.ps1
```

You should see `(.venv)` at the start of your prompt.

### Step 3: Start Backend Server
```powershell
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**You should see:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### Step 4: Verify It's Working
Open http://localhost:8000/api/health in your browser.

You should see:
```json
{"status":"ok","data_dir":"C:\\Users\\holme\\Documents\\PDA\\data"}
```

## ✅ Success!
If you see the JSON response above, your backend is running!

**Keep this PowerShell window open** - closing it will stop the server.

## 🔄 Now Start Frontend (Separate Terminal)

Open a **NEW** PowerShell window:

```powershell
cd C:\Users\holme\Documents\PDA\frontend
npm run dev
```

Then open http://localhost:3000 in your browser.

## ❌ Troubleshooting

**"No module named 'uvicorn'"**
```powershell
pip install uvicorn[standard]
```

**"No module named 'fastapi'"**
```powershell
pip install -e .
```

**"Execution policy error"**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Port 8000 already in use**
- Find what's using it: `netstat -ano | findstr :8000`
- Or use a different port: `--port 8001`
- Update frontend `.env`: `NEXT_PUBLIC_API_URL=http://localhost:8001`
