"""Authentication API routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.auth import authenticate, require_auth, revoke_token

logger = logging.getLogger(__name__)
router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    display_name: str


class LogoutResponse(BaseModel):
    status: str


@router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Authenticate with username/password and receive a bearer token."""
    session = authenticate(request.username, request.password)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    return LoginResponse(
        token=session["token"],
        username=session["username"],
        display_name=session["display_name"],
    )


@router.post("/auth/logout", response_model=LogoutResponse)
async def logout(session: dict = Depends(require_auth)):
    """Revoke the current session token."""
    revoke_token(session["token"])
    return LogoutResponse(status="logged_out")


@router.get("/auth/me")
async def me(session: dict = Depends(require_auth)):
    """Return the current authenticated user."""
    return {
        "username": session["username"],
        "display_name": session["display_name"],
    }
