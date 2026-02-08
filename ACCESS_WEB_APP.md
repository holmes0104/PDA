# 🌐 Access Your Working PDA Web App

## Step 1: Start Backend Server

Open **PowerShell Terminal 1** and run:

```powershell
cd C:\Users\holme\Documents\PDA
.venv\Scripts\Activate.ps1
cd backend
python -m uvicorn main:app --reload --port 8000
```

**You should see:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

**✅ Backend is running when you see this!**

## Step 2: Start Frontend Server

Open **PowerShell Terminal 2** (NEW window) and run:

```powershell
cd C:\Users\holme\Documents\PDA\frontend
npm run dev
```

**You should see:**
```
  ▲ Next.js 15.0.7
  - Local:        http://localhost:3000
```

**✅ Frontend is running when you see this!**

## Step 3: Access the Web App

Open your browser and go to:

### 🎯 **Main App: http://localhost:3000**

This is your web interface where you can:
- Upload PDF brochures
- Add product page URLs
- Run audits
- Download reports

### 🔧 **API Documentation: http://localhost:8000/docs**

This shows all available API endpoints (Swagger UI)

### ❤️ **Health Check: http://localhost:8000/api/health**

Should return: `{"status":"ok","data_dir":"..."}`

## Quick Start Script (Both Servers)

If you want to start both at once, use:

```powershell
.\run_dev.ps1
```

Or manually in two terminals as shown above.

## ✅ Verification Checklist

- [ ] Backend running on port 8000
- [ ] Frontend running on port 3000
- [ ] Can access http://localhost:3000
- [ ] Can see upload form
- [ ] Health check works: http://localhost:8000/api/health

## 🎉 You're Ready!

Once both servers are running, you can:
1. Upload a PDF at http://localhost:3000
2. Optionally add a product URL
3. Click "Upload PDF & Scrape URL"
4. Follow the pipeline steps
5. Download your reports!
