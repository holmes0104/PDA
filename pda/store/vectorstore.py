"""ChromaDB wrapper for chunk storage and retrieval with configurable embeddings."""

from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from pda.schemas.models import DocumentChunk


class VectorStore:
    """
    Store DocumentChunks in ChromaDB with configurable embedding (OpenAI or sentence-transformers).
    """

    def __init__(
        self,
        collection_name: str = "pda_chunks",
        persist_directory: str | Path | None = None,
        embedding_model: str = "openai",
        openai_api_key: str | None = None,
    ):
        """
        embedding_model: "openai" (uses text-embedding-3-small) or "sentence-transformers".
        openai_api_key: required when embedding_model == "openai".
        """
        self._embedding_model = embedding_model
        self._openai_api_key = openai_api_key
        self._collection_name = collection_name
        self._persist_directory = str(persist_directory) if persist_directory else None
        self._client = chromadb.PersistentClient(
            path=self._persist_directory or "./chroma_data",
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._embedding_fn = self._get_embedding_function()
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._embedding_fn,
            metadata={"description": "PDA document chunks"},
        )

    def _get_embedding_function(self) -> Any:
        try:
            if self._embedding_model == "openai":
                from chromadb.utils import embedding_functions
                return embedding_functions.OpenAIEmbeddingFunction(
                    api_key=self._openai_api_key or "",
                    model_name="text-embedding-3-small",
                )
            if self._embedding_model == "sentence-transformers":
                from chromadb.utils import embedding_functions
                return embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="all-MiniLM-L6-v2",
                )
        except Exception:
            pass
        from chromadb.utils import embedding_functions
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2",
        )

    def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        """Embed and store chunks. Re-adding same chunk_id will overwrite."""
        if not chunks:
            return
        ids = [c.chunk_id for c in chunks]
        documents = [c.text for c in chunks]
        metadatas = [
            {
                "source_file": c.source_file,
                "page_number": c.page_number if c.page_number is not None else -1,
                "section_heading": c.section_heading or "",
            }
            for c in chunks
        ]
        self._collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def query(
        self,
        query_text: str,
        n_results: int = 10,
        where: dict | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return similar chunks. Each item has chunk_id, text, distance, metadata.
        """
        result = self._collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        out: list[dict[str, Any]] = []
        if not result["ids"] or not result["ids"][0]:
            return out
        for i, chunk_id in enumerate(result["ids"][0]):
            doc = (result["documents"][0][i]) if result["documents"] else ""
            meta = (result["metadatas"][0][i]) if result["metadatas"] else {}
            dist = (result["distances"][0][i]) if result.get("distances") else None
            out.append({
                "chunk_id": chunk_id,
                "text": doc,
                "distance": dist,
                "metadata": meta,
            })
        return out

    def get_by_ids(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        """Fetch chunks by id."""
        if not chunk_ids:
            return []
        result = self._collection.get(
            ids=chunk_ids,
            include=["documents", "metadatas"],
        )
        out: list[dict[str, Any]] = []
        for i, chunk_id in enumerate(result["ids"]):
            doc = result["documents"][i] if result["documents"] else ""
            meta = result["metadatas"][i] if result["metadatas"] else {}
            out.append({"chunk_id": chunk_id, "text": doc, "metadata": meta})
        return out
