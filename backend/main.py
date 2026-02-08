"""FastAPI backend for PDA web app."""

import logging
import sys
import time
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from pda.config import get_settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

settings = get_settings()

app = FastAPI(
    title="PDA API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# ---------------------------------------------------------------------------
# CORS — controlled via CORS_ORIGINS env var
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Basic in-memory rate limiter (per IP, 30 requests / 60 s for mutating routes)
# ---------------------------------------------------------------------------
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 30  # max requests per window
_rate_store: dict[str, list[float]] = defaultdict(list)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Simple sliding-window rate limiter for non-GET routes."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = _rate_store[client_ip]
    # Prune old entries
    _rate_store[client_ip] = [t for t in window if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_store[client_ip]) >= RATE_LIMIT_MAX:
        return Response(
            content='{"detail":"Rate limit exceeded. Try again later."}',
            status_code=429,
            media_type="application/json",
        )
    _rate_store[client_ip].append(now)
    return await call_next(request)


# ---------------------------------------------------------------------------
# Health & root
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str
    data_dir: str


@app.get("/health", response_model=HealthResponse)
@app.get("/api/health", response_model=HealthResponse)
async def health():
    """Health check endpoint (Render probes /health)."""
    return HealthResponse(status="ok", data_dir=str(settings.data_dir))


@app.get("/api/")
async def root():
    """API root."""
    return {"message": "PDA API", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
from backend.routes import audit, downloads, factsheet, ingest, simulate, verify  # noqa: E402

app.include_router(ingest.router, prefix="/api", tags=["ingest"])
app.include_router(factsheet.router, prefix="/api", tags=["factsheet"])
app.include_router(audit.router, prefix="/api", tags=["audit"])
app.include_router(simulate.router, prefix="/api", tags=["simulate"])
app.include_router(verify.router, prefix="/api", tags=["verify"])
app.include_router(downloads.router, prefix="/api", tags=["downloads"])
