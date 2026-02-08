# Troubleshooting: pip install stuck

If `pip install uvicorn[standard]` is stuck, try these solutions:

## Solution 1: Use pip with timeout and verbose output

```powershell
cd C:\Users\holme\Documents\PDA
.venv\Scripts\Activate.ps1

# Install with verbose output to see what's happening
python -m pip install uvicorn[standard] --verbose --timeout 60
```

## Solution 2: Install without extras first

```powershell
# Install basic uvicorn first
python -m pip install uvicorn

# Then install extras
python -m pip install websockets httptools
```

## Solution 3: Use a different index (if PyPI is slow)

```powershell
# Use PyPI mirror
python -m pip install uvicorn[standard] -i https://pypi.org/simple
```

## Solution 4: Check if it's actually working

The installation might be downloading large files. Check:
- Your internet connection
- Windows Firewall isn't blocking pip
- Antivirus isn't blocking pip

## Solution 5: Install from requirements.txt

```powershell
# Make sure requirements.txt has uvicorn
python -m pip install -r requirements.txt
```

## Solution 6: Manual installation check

```powershell
# Check if uvicorn is already installed
python -m pip list | findstr uvicorn

# If it shows uvicorn, you can try starting the server anyway
cd backend
python -m uvicorn main:app --reload --port 8000
```

## Quick Test

Try this to see if pip is working at all:

```powershell
python -m pip install --upgrade pip
```

If this also hangs, there's a network/firewall issue.
