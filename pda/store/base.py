"""Abstract vector store interface (Protocol) for PDA."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pda.schemas.models import DocumentChunk


@runtime_checkable
class VectorStoreBackend(Protocol):
    """
    Protocol that both ChromaVectorStore and PgVectorStore implement.

    All methods operate on ``DocumentChunk`` objects (the internal chunk
    representation used throughout the PDA pipeline).
    """

    def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        """Upsert chunks (text + metadata). Re-adding the same chunk_id overwrites."""
        ...

    def query(
        self,
        query_text: str,
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return the *n_results* most similar chunks.

        Each item is a dict with at least:
        ``chunk_id``, ``text``, ``distance``, ``metadata``.
        """
        ...

    def get_by_ids(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        """Fetch chunks by their IDs."""
        ...
