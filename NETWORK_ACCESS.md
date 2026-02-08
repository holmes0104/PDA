# 🌐 Making PDA Accessible on Network/Internet

## Current Status

**`http://172.22.240.1:3000`** is a **local network IP** (likely Docker bridge network). It's:
- ❌ **NOT accessible from the internet**
- ⚠️ **May not be accessible from other devices** (depends on network setup)
- ✅ **Only accessible from your computer** (if it's a Docker network IP)

## Option 1: Access on Local Network (Same WiFi)

### Step 1: Find Your Real Local IP

```powershell
# In PowerShell
ipconfig | findstr IPv4
```

Look for your WiFi/Ethernet adapter IP (usually starts with `192.168.x.x` or `10.x.x.x`)

### Step 2: Update Configuration

1. **Update Backend CORS** to allow your local IP
2. **Start Next.js** with `-H 0.0.0.0` to bind to all interfaces

### Step 3: Start Servers

**Backend:**
```powershell
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend:**
```powershell
cd frontend
npm run dev -- -H 0.0.0.0
```

### Step 4: Access from Other Devices

On other devices on the same WiFi:
- Use your computer's local IP: `http://192.168.x.x:3000`
- Example: `http://192.168.1.100:3000`

## Option 2: Access from Internet (Any Device)

### Using ngrok (Easiest)

1. **Install ngrok**: https://ngrok.com/download

2. **Start your servers** (localhost)

3. **Create tunnel:**
```powershell
ngrok http 3000
```

4. **Get public URL** (e.g., `https://abc123.ngrok.io`)

5. **Update backend CORS** to include ngrok URL

### Using Cloudflare Tunnel (Free)

```powershell
# Install cloudflared
# Create tunnel
cloudflared tunnel --url http://localhost:3000
```

### Deploy to Cloud (Production)

- **Vercel** (for Next.js frontend)
- **Railway/Render** (for FastAPI backend)
- **Docker Compose** on a VPS

## Quick Fix: Update CORS for Local Network

See `UPDATE_CORS.md` for instructions.
