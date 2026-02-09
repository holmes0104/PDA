"""Generation job storage — Postgres (preferred) or file-based fallback."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Protocol

from pda.config import get_settings
from pda.jobs.models import GenerationJob, JobStatus

logger = logging.getLogger(__name__)


class JobStore(Protocol):
    def create(self, job: GenerationJob) -> GenerationJob: ...
    def get(self, job_id: str) -> GenerationJob | None: ...
    def get_by_idempotency_key(self, key: str) -> GenerationJob | None: ...
    def update(self, job: GenerationJob) -> None: ...


# ---------------------------------------------------------------------------
# Postgres implementation
# ---------------------------------------------------------------------------

class PostgresJobStore:
    """Persist jobs in Postgres. Survives restarts."""

    def __init__(self, database_url: str):
        self._url = database_url
        self._conn = self._connect()
        self._ensure_table()

    def _connect(self):
        try:
            import psycopg
            conn = psycopg.connect(self._url, autocommit=True)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pda_generation_jobs (
                    job_id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INT NOT NULL DEFAULT 0,
                    params JSONB NOT NULL DEFAULT '{}',
                    error_message TEXT,
                    drafts JSONB,
                    metadata JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pda_generation_jobs_idempotency
                ON pda_generation_jobs (idempotency_key, status)
            """)
            return conn
        except ImportError:
            raise ImportError(
                "psycopg required for Postgres job store. pip install 'psycopg[binary]'"
            )

    def _ensure_table(self) -> None:
        pass  # done in _connect

    def create(self, job: GenerationJob) -> GenerationJob:
        row = (
            job.job_id,
            job.product_id,
            job.idempotency_key,
            job.status.value,
            job.progress,
            json.dumps(job.params),
            job.error_message,
            json.dumps(job.drafts) if job.drafts else None,
            json.dumps(job.metadata) if job.metadata else None,
        )
        self._conn.execute(
            """
            INSERT INTO pda_generation_jobs
            (job_id, product_id, idempotency_key, status, progress, params,
             error_message, drafts, metadata, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s::jsonb, NOW(), NOW())
            """,
            row,
        )
        return job

    def get(self, job_id: str) -> GenerationJob | None:
        row = self._conn.execute(
            """
            SELECT job_id, product_id, idempotency_key, status, progress, params,
                   error_message, drafts, metadata, created_at, updated_at
            FROM pda_generation_jobs WHERE job_id = %s
            """,
            (job_id,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_job(row)

    def get_by_idempotency_key(self, key: str) -> GenerationJob | None:
        """Return in-flight job (queued or running) for this key, if any."""
        row = self._conn.execute(
            """
            SELECT job_id, product_id, idempotency_key, status, progress, params,
                   error_message, drafts, metadata, created_at, updated_at
            FROM pda_generation_jobs
            WHERE idempotency_key = %s AND status IN ('queued', 'running')
            ORDER BY created_at DESC LIMIT 1
            """,
            (key,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_job(row)

    def update(self, job: GenerationJob) -> None:
        drafts_json = json.dumps(job.drafts) if job.drafts else None
        metadata_json = json.dumps(job.metadata) if job.metadata else None
        self._conn.execute(
            """
            UPDATE pda_generation_jobs SET
                status = %s, progress = %s, error_message = %s,
                drafts = COALESCE(%s::jsonb, drafts), metadata = COALESCE(%s::jsonb, metadata),
                updated_at = NOW()
            WHERE job_id = %s
            """,
            (job.status.value, job.progress, job.error_message, drafts_json, metadata_json, job.job_id),
        )

    def _row_to_job(self, row) -> GenerationJob:
        return GenerationJob(
            job_id=row[0],
            product_id=row[1],
            idempotency_key=row[2],
            status=JobStatus(row[3]),
            progress=row[4],
            params=row[5] if isinstance(row[5], dict) else (json.loads(row[5]) if row[5] else {}),
            error_message=row[6],
            drafts=row[7] if isinstance(row[7], dict) else (json.loads(row[7]) if row[7] else None),
            metadata=row[8] if isinstance(row[8], dict) else (json.loads(row[8]) if row[8] else None),
            created_at=row[9],
            updated_at=row[10],
        )


# ---------------------------------------------------------------------------
# File-based implementation (fallback when no Postgres)
# ---------------------------------------------------------------------------

class FileJobStore:
    """Persist jobs as JSON files. Survives restarts within same data dir."""

    def __init__(self, data_dir: Path):
        self._dir = Path(data_dir) / "jobs"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / "index.json"
        self._index: dict[str, str] = self._load_index()

    def _load_index(self) -> dict[str, str]:
        """Maps idempotency_key -> job_id for lookup."""
        if self._index_path.exists():
            try:
                with open(self._index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_index(self) -> None:
        with open(self._index_path, "w", encoding="utf-8") as f:
            json.dump(self._index, f, indent=2)

    def _job_path(self, job_id: str) -> Path:
        return self._dir / f"{job_id}.json"

    def create(self, job: GenerationJob) -> GenerationJob:
        self._index[job.idempotency_key] = job.job_id
        self._save_index()
        self._write_job(job)
        return job

    def get(self, job_id: str) -> GenerationJob | None:
        path = self._job_path(job_id)
        if not path.exists():
            return None
        return self._read_job(path)

    def get_by_idempotency_key(self, key: str) -> GenerationJob | None:
        job_id = self._index.get(key)
        if not job_id:
            return None
        return self.get(job_id)

    def update(self, job: GenerationJob) -> None:
        self._write_job(job)

    def _write_job(self, job: GenerationJob) -> None:
        path = self._job_path(job.job_id)
        data = job.model_dump(mode="json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def _read_job(self, path: Path) -> GenerationJob:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return GenerationJob.model_validate(data)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_store: JobStore | None = None


def get_job_store() -> JobStore:
    """Return singleton job store (Postgres if configured, else file-based)."""
    global _store
    if _store is not None:
        return _store
    settings = get_settings()
    if settings.pda_database_url:
        try:
            _store = PostgresJobStore(settings.pda_database_url)
            logger.info("Using Postgres job store")
        except Exception as e:
            logger.warning("Postgres job store failed (%s), falling back to file store", e)
            _store = FileJobStore(settings.data_dir)
    else:
        _store = FileJobStore(settings.data_dir)
        logger.info("Using file-based job store (PDA_DATA_DIR/jobs)")
    return _store


def _new_job_id() -> str:
    return f"job_{uuid.uuid4().hex[:16]}"
