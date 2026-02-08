# Update CORS for Network Access

## Current Issue

Backend only allows `localhost:3000`. To access from other devices, update CORS.

## Solution: Update Backend CORS

Edit `backend/main.py`:

```python
# Change this:
allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],

# To this (for local network):
allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://192.168.*:*"],

# Or allow all (less secure, for testing):
allow_origins=["*"],
```

## Start Frontend on All Interfaces

```powershell
cd frontend
npm run dev -- -H 0.0.0.0
```

This makes Next.js accessible from other devices on your network.

## Find Your Local IP

```powershell
ipconfig | findstr IPv4
```

Use that IP on other devices: `http://YOUR_IP:3000`
