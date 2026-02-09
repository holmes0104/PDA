"""Product content drafts storage — Postgres or file-based fallback."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from pda.config import get_settings

logger = logging.getLogger(__name__)


class DraftsStore(Protocol):
    def save(
        self,
        product_id: str,
        params_hash: str,
        tone: str,
        length: str,
        audience: str,
        drafts_json: dict[str, Any],
    ) -> str: ...
    def get_latest(self, product_id: str) -> dict[str, Any] | None: ...


# ---------------------------------------------------------------------------
# Postgres implementation
# ---------------------------------------------------------------------------

class PostgresDraftsStore:
    """Persist drafts in product_content_drafts table."""

    def __init__(self, database_url: str):
        self._url = database_url
        self._conn = self._connect()

    def _connect(self):
        try:
            import psycopg
            conn = psycopg.connect(self._url, autocommit=True)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS product_content_drafts (
                    id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    params_hash TEXT NOT NULL,
                    tone TEXT NOT NULL,
                    length TEXT NOT NULL,
                    audience TEXT NOT NULL,
                    drafts_json JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_product_content_drafts_product
                ON product_content_drafts (product_id, created_at DESC)
            """)
            return conn
        except ImportError:
            raise ImportError(
                "psycopg required for Postgres drafts store. pip install 'psycopg[binary]'"
            )

    def save(
        self,
        product_id: str,
        params_hash: str,
        tone: str,
        length: str,
        audience: str,
        drafts_json: dict[str, Any],
    ) -> str:
        draft_id = f"draft_{uuid.uuid4().hex[:16]}"
        self._conn.execute(
            """
            INSERT INTO product_content_drafts
            (id, product_id, params_hash, tone, length, audience, drafts_json, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
            """,
            (draft_id, product_id, params_hash, tone, length, audience, json.dumps(drafts_json)),
        )
        return draft_id

    def get_latest(self, product_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT drafts_json FROM product_content_drafts
            WHERE product_id = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (product_id,),
        ).fetchone()
        if not row:
            return None
        data = row[0]
        return data if isinstance(data, dict) else json.loads(data)


# ---------------------------------------------------------------------------
# File-based implementation
# ---------------------------------------------------------------------------

class FileDraftsStore:
    """Persist drafts as JSON files. One file per product (latest overwrites)."""

    def __init__(self, data_dir: Path):
        self._dir = Path(data_dir) / "drafts"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / "index.json"
        self._index: dict[str, str] = self._load_index()

    def _load_index(self) -> dict[str, str]:
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

    def _draft_path(self, product_id: str) -> Path:
        return self._dir / f"{product_id}.json"

    def save(
        self,
        product_id: str,
        params_hash: str,
        tone: str,
        length: str,
        audience: str,
        drafts_json: dict[str, Any],
    ) -> str:
        draft_id = f"draft_{uuid.uuid4().hex[:16]}"
        payload = {
            "id": draft_id,
            "product_id": product_id,
            "params_hash": params_hash,
            "tone": tone,
            "length": length,
            "audience": audience,
            "drafts_json": drafts_json,
            "created_at": datetime.utcnow().isoformat(),
        }
        path = self._draft_path(product_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        self._index[product_id] = draft_id
        self._save_index()
        return draft_id

    def get_latest(self, product_id: str) -> dict[str, Any] | None:
        path = self._draft_path(product_id)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("drafts_json")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_store: DraftsStore | None = None


def get_drafts_store() -> DraftsStore:
    """Return singleton drafts store (Postgres if configured, else file-based)."""
    global _store
    if _store is not None:
        return _store
    settings = get_settings()
    if settings.pda_database_url:
        try:
            _store = PostgresDraftsStore(settings.pda_database_url)
            logger.info("Using Postgres drafts store")
        except Exception as e:
            logger.warning("Postgres drafts store failed (%s), falling back to file store", e)
            _store = FileDraftsStore(settings.data_dir)
    else:
        _store = FileDraftsStore(settings.data_dir)
        logger.info("Using file-based drafts store (PDA_DATA_DIR/drafts)")
    return _store
