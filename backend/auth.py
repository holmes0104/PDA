"""Authentication layer for PDA.

Simple token-based auth with hardcoded credentials.
Tokens are stored in-memory and expire after TOKEN_TTL_SECONDS.
"""

import hashlib
import logging
import secrets
import time
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
_SALT = "pda-vaisala-2026"


def _hash_pw(password: str) -> str:
    return hashlib.sha256(f"{_SALT}:{password}".encode()).hexdigest()


# ---------------------------------------------------------------------------
# Credential store  (username -> password_hash)
# ---------------------------------------------------------------------------
USERS: dict[str, dict] = {
    "admin": {
        "password_hash": _hash_pw("Vaisala2026!"),
        "display_name": "Admin",
    },
    "tnguyen": {
        "password_hash": _hash_pw("PDA@Holmes"),
        "display_name": "Thanh Nguyen",
    },
}

# ---------------------------------------------------------------------------
# Token store  (token -> {username, display_name, created_at})
# ---------------------------------------------------------------------------
TOKEN_TTL_SECONDS = 24 * 60 * 60  # 24 hours
_tokens: dict[str, dict] = {}

_bearer_scheme = HTTPBearer(auto_error=False)


def authenticate(username: str, password: str) -> Optional[dict]:
    """Verify credentials and return a session dict, or None on failure."""
    user = USERS.get(username.lower())
    if not user:
        return None
    if user["password_hash"] != _hash_pw(password):
        return None

    token = secrets.token_hex(32)
    session = {
        "token": token,
        "username": username.lower(),
        "display_name": user["display_name"],
        "created_at": time.time(),
    }
    _tokens[token] = session
    logger.info("User '%s' authenticated", username)
    return session


def _prune_expired():
    """Remove expired tokens."""
    now = time.time()
    expired = [t for t, s in _tokens.items() if now - s["created_at"] > TOKEN_TTL_SECONDS]
    for t in expired:
        del _tokens[t]


def validate_token(token: str) -> Optional[dict]:
    """Return session dict if valid, else None."""
    _prune_expired()
    session = _tokens.get(token)
    if not session:
        return None
    if time.time() - session["created_at"] > TOKEN_TTL_SECONDS:
        del _tokens[token]
        return None
    return session


def revoke_token(token: str) -> bool:
    """Revoke (logout) a token. Returns True if it existed."""
    return _tokens.pop(token, None) is not None


# ---------------------------------------------------------------------------
# FastAPI dependency — require auth on protected routes
# ---------------------------------------------------------------------------
# Paths that do NOT require authentication
PUBLIC_PATHS = {
    "/health",
    "/api/health",
    "/api/",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
    "/api/auth/login",
}


async def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """FastAPI dependency: extract and validate bearer token.

    Returns the session dict on success, raises 401 otherwise.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session = validate_token(credentials.credentials)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return session
