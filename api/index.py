"""Vercel serverless entrypoint: expose the FastAPI app for deployment."""
from backend.main import app

__all__ = ["app"]
