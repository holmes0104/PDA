"""Generation job schema and status."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class GenerationJob(BaseModel):
    """Web content generation job — persisted for async polling."""

    job_id: str = ""
    product_id: str = ""
    idempotency_key: str = ""
    status: JobStatus = JobStatus.QUEUED
    progress: int = Field(default=0, ge=0, le=100)
    params: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    drafts: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
