"""Postgres + pgvector vector store implementation."""

from __future__ import annotations

import json
import logging
from typing import Any

from pda.schemas.models import DocumentChunk

logger = logging.getLogger(__name__)

# Embedding dimension for OpenAI text-embedding-3-small
_OPENAI_DIM = 1536
# Embedding dimension for all-MiniLM-L6-v2
_MINILM_DIM = 384


class PgVectorStore:
    """
    Vector store backed by Postgres + pgvector.

    Requires:
      - ``psycopg[binary]`` (or ``psycopg2-binary``)
      - ``pgvector`` Python package
      - A Postgres server with the ``vector`` extension enabled.

    The store creates a table ``pda_chunks`` (configurable) with columns:
      project_id, chunk_id (PK pair), embedding vector, text, metadata jsonb.
    """

    def __init__(
        self,
        database_url: str,
        collection_name: str = "pda_chunks",
        embedding_model: str = "openai",
        openai_api_key: str | None = None,
        project_id: str = "default",
    ):
        self._database_url = database_url
        self._table = collection_name
        self._embedding_model = embedding_model
        self._openai_api_key = openai_api_key
        self._project_id = project_id
        self._dim = _OPENAI_DIM if embedding_model == "openai" else _MINILM_DIM

        self._embed_fn = self._build_embed_fn()
        self._conn = self._connect()
        self._ensure_table()

    # ── connection / schema ──────────────────────────────────────────────

    def _connect(self):
        try:
            import psycopg

            conn = psycopg.connect(self._database_url, autocommit=True)
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            return conn
        except ImportError:
            raise ImportError(
                "psycopg is required for pgvector backend. "
                "Install with: pip install 'psycopg[binary]' pgvector"
            )

    def _ensure_table(self) -> None:
        self._conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._table} (
                project_id TEXT NOT NULL,
                chunk_id   TEXT NOT NULL,
                embedding  vector({self._dim}),
                text       TEXT NOT NULL DEFAULT '',
                metadata   JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                PRIMARY KEY (project_id, chunk_id)
            )
        """)
        # Create an ivfflat index if it doesn't exist (best-effort)
        try:
            self._conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self._table}_embedding
                ON {self._table}
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
            """)
        except Exception:
            pass  # index creation may fail on small tables; that's fine

    # ── embedding ────────────────────────────────────────────────────────

    def _build_embed_fn(self):
        if self._embedding_model == "openai":
            return self._embed_openai
        return self._embed_st

    def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        from openai import OpenAI

        client = OpenAI(api_key=self._openai_api_key or "")
        resp = client.embeddings.create(input=texts, model="text-embedding-3-small")
        return [d.embedding for d in resp.data]

    def _embed_st(self, texts: list[str]) -> list[list[float]]:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("all-MiniLM-L6-v2")
        return model.encode(texts, show_progress_bar=False).tolist()

    # ── public API (matches VectorStoreBackend protocol) ─────────────────

    def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        if not chunks:
            return
        texts = [c.text for c in chunks]
        embeddings = self._embed_fn(texts)
        for chunk, emb in zip(chunks, embeddings):
            meta = {
                "source_file": chunk.source_file,
                "page_number": chunk.page_number if chunk.page_number is not None else -1,
                "section_heading": chunk.section_heading or "",
            }
            self._conn.execute(
                f"""
                INSERT INTO {self._table} (project_id, chunk_id, embedding, text, metadata)
                VALUES (%s, %s, %s::vector, %s, %s::jsonb)
                ON CONFLICT (project_id, chunk_id) DO UPDATE
                SET embedding = EXCLUDED.embedding,
                    text = EXCLUDED.text,
                    metadata = EXCLUDED.metadata
                """,
                (
                    self._project_id,
                    chunk.chunk_id,
                    str(emb),
                    chunk.text,
                    json.dumps(meta),
                ),
            )

    def query(
        self,
        query_text: str,
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        emb = self._embed_fn([query_text])[0]
        result = self._conn.execute(
            f"""
            SELECT chunk_id, text, metadata,
                   embedding <=> %s::vector AS distance
            FROM {self._table}
            WHERE project_id = %s
            ORDER BY distance ASC
            LIMIT %s
            """,
            (str(emb), self._project_id, n_results),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in result:
            out.append({
                "chunk_id": row[0],
                "text": row[1],
                "metadata": row[2] if isinstance(row[2], dict) else json.loads(row[2]),
                "distance": float(row[3]),
            })
        return out

    def get_by_ids(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        if not chunk_ids:
            return []
        placeholders = ", ".join(["%s"] * len(chunk_ids))
        result = self._conn.execute(
            f"""
            SELECT chunk_id, text, metadata
            FROM {self._table}
            WHERE project_id = %s AND chunk_id IN ({placeholders})
            """,
            (self._project_id, *chunk_ids),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in result:
            out.append({
                "chunk_id": row[0],
                "text": row[1],
                "metadata": row[2] if isinstance(row[2], dict) else json.loads(row[2]),
            })
        return out
