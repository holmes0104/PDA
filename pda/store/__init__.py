"""Stage 2 — chunk storage and retrieval (ChromaDB or pgvector)."""

from __future__ import annotations

from typing import Any

from pda.store.base import VectorStoreBackend
from pda.store.vectorstore import VectorStore


def get_vector_store(
    backend: str = "chroma",
    *,
    collection_name: str = "pda_chunks",
    persist_directory: str | None = None,
    embedding_model: str = "openai",
    openai_api_key: str | None = None,
    database_url: str | None = None,
    project_id: str = "default",
) -> VectorStoreBackend:
    """
    Factory that returns the configured vector store backend.

    backend: ``"chroma"`` (default) or ``"pgvector"``.
    """
    if backend == "pgvector":
        from pda.store.pgvector_store import PgVectorStore

        if not database_url:
            raise ValueError("database_url is required for pgvector backend")
        return PgVectorStore(
            database_url=database_url,
            collection_name=collection_name,
            embedding_model=embedding_model,
            openai_api_key=openai_api_key,
            project_id=project_id,
        )
    # Default: Chroma
    return VectorStore(
        collection_name=collection_name,
        persist_directory=persist_directory,
        embedding_model=embedding_model,
        openai_api_key=openai_api_key,
    )


__all__ = ["VectorStore", "VectorStoreBackend", "get_vector_store"]
