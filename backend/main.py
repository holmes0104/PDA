"""FastAPI backend for PDA web app — Designed for Vaisala by Thanh Nguyen (Holmes)."""

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
from backend.auth import PUBLIC_PATHS, validate_token

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

settings = get_settings()

app = FastAPI(
    title="PDA API — Vaisala",
    description="LLM-Ready Product Content Generator. Designed for Vaisala by Thanh Nguyen (Holmes).",
    version="0.3.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)


# ---------------------------------------------------------------------------
# Authentication middleware — reject unauthenticated requests to protected paths
# ---------------------------------------------------------------------------
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Enforce bearer-token auth on all non-public API routes."""
    path = request.url.path.rstrip("/")

    # Allow public paths, OPTIONS (CORS preflight), and Swagger/OpenAPI assets
    if (
        request.method == "OPTIONS"
        or path in PUBLIC_PATHS
        or f"{path}/" in PUBLIC_PATHS
        or path.startswith("/api/docs")
        or path.startswith("/api/redoc")
        or path.startswith("/api/openapi")
    ):
        return await call_next(request)

    # Everything under /api/ requires auth (except the above)
    if path.startswith("/api/"):
        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return Response(
                content='{"detail":"Authentication required"}',
                status_code=401,
                media_type="application/json",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = auth_header.split(" ", 1)[1]
        session = validate_token(token)
        if not session:
            return Response(
                content='{"detail":"Invalid or expired token"}',
                status_code=401,
                media_type="application/json",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return await call_next(request)


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
# CORS — added LAST so it is the OUTERMOST middleware.
# In Starlette, add_middleware uses LIFO: last-added = outermost.
# @app.middleware("http") also calls add_middleware internally.
# CORSMiddleware MUST wrap auth & rate-limit so that CORS headers
# are present on ALL responses (including 401/429 error responses).
# ---------------------------------------------------------------------------
cors_origins = settings.cors_origin_list
cors_origin_regex = settings.cors_origin_regex
logger.info("CORS configured for origins: %s", cors_origins)
if cors_origin_regex:
    logger.info("CORS origin regex: %s", cors_origin_regex)

# Log vector-store backend so operators can verify the deployment config.
_vb = settings.pda_vector_backend
if _vb == "pgvector":
    logger.info(
        "Vector store: pgvector (Postgres) — stateless-safe. "
        "DATABASE_URL %s",
        "configured" if settings.pda_database_url else "*** NOT SET — will fail at query time ***",
    )
elif _vb == "chroma":
    logger.info(
        "Vector store: ChromaDB on-disk (persist_dir=%s). "
        "Requires persistent disk on the backend host.",
        settings.chroma_dir,
    )
else:
    logger.warning("Vector store: unknown backend '%s' — defaulting to chroma.", _vb)
cors_kw: dict = {
    "allow_origins": cors_origins,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
    "expose_headers": ["*"],
}
if cors_origin_regex:
    cors_kw["allow_origin_regex"] = cors_origin_regex
app.add_middleware(CORSMiddleware, **cors_kw)


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
    return {
        "message": "PDA API — Designed for Vaisala by Thanh Nguyen (Holmes)",
        "version": "0.2.0",
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
from backend.routes import audit, auth, content_pack, downloads, factsheet, ingest, pipeline, simulate, verify, web_content  # noqa: E402

app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(ingest.router, prefix="/api", tags=["ingest"])
app.include_router(pipeline.router, prefix="/api", tags=["pipeline"])
app.include_router(factsheet.router, prefix="/api", tags=["factsheet"])
app.include_router(content_pack.router, prefix="/api", tags=["content_pack"])
app.include_router(audit.router, prefix="/api", tags=["audit"])
app.include_router(simulate.router, prefix="/api", tags=["simulate"])
app.include_router(verify.router, prefix="/api", tags=["verify"])
app.include_router(downloads.router, prefix="/api", tags=["downloads"])
app.include_router(web_content.router, prefix="/api", tags=["web_content"])
