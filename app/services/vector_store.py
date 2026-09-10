"""The vector store: what a stored record is, not how Pinecone is reached.

This module owns the whole record shape -- how a Chunk's id is derived, which
Namespace it lands in, and what its metadata holds -- so no caller has to know
any of it. It owns the read side too, which is what keeps the two in step: the
key written as ``chunk_text`` is decoded back into a Chunk in the same file.

Connection lifecycle lives in ``app.services.pinecone``.
"""

import hashlib
from pathlib import Path

from pinecone import AsyncIndex

from app.models.schemas import Chunk, ConvertedDocument, SearchHit

# Pinecone caps a single delete call; forget() batches to stay under it.
_DELETE_BATCH = 1000


class VectorStoreConfigError(RuntimeError):
    """Raised when the Pinecone client is used before it is configured."""


def _document_id(source: str) -> str:
    """Stable id for a Source, short enough to prefix a Chunk id."""
    return hashlib.sha1(source.encode()).hexdigest()[:16]


def _namespace_for(source: str) -> str:
    """Partition vectors by the Document's containing folder.

    URLs have no folder to key off of, so they fall back to the default
    (empty-string) namespace.
    """
    if "://" in source:
        return ""
    return Path(source).parent.name


class PineconeVectorStore:
    """Stores and retrieves Chunks as Pinecone records."""

    def __init__(self, index: AsyncIndex) -> None:
        self._index = index

    async def store(
        self, document: ConvertedDocument, vectors: list[list[float]]
    ) -> None:
        """Write one Document's Chunks, one record per Chunk."""
        doc_id = _document_id(document.source)
        records = [
            {
                "id": f"{doc_id}:{i}",
                "values": vector,
                "metadata": {
                    "source": document.source,
                    "chunk_text": chunk.text,
                    "headings": chunk.headings,
                },
            }
            for i, (chunk, vector) in enumerate(zip(document.chunks, vectors))
        ]
        if not records:
            return
        await self._index.upsert(
            vectors=records, namespace=_namespace_for(document.source)
        )

    async def stored_ids(self, source: str) -> list[str]:
        """Every record id currently stored for a Source.

        Ids carry the Document id as a prefix, so this answers "is this Source
        already ingested, and how much of it" with one listing and no reads.
        """
        prefix = f"{_document_id(source)}:"
        namespace = _namespace_for(source)

        ids: list[str] = []
        token: str | None = None
        while True:
            page = await self._index.list_paginated(
                prefix=prefix, namespace=namespace, pagination_token=token
            )
            ids.extend(vector.id for vector in (page.vectors or []))
            token = getattr(page.pagination, "next", None) if page.pagination else None
            if not token:
                return ids

    async def stored_chunks(self, source: str) -> int:
        """How many Chunks are stored for a Source; 0 means it was never ingested."""
        return len(await self.stored_ids(source))

    async def forget(self, source: str) -> int:
        """Delete every record stored for a Source, returning how many.

        Re-ingesting a Document that shrank would otherwise leave the records
        past its new end behind, still pointing at text the Document no longer
        contains. Ids are prefixed with the Document id precisely so they can be
        listed and removed without knowing how many there were.
        """
        ids = await self.stored_ids(source)
        if not ids:
            return 0

        namespace = _namespace_for(source)
        for start in range(0, len(ids), _DELETE_BATCH):
            await self._index.delete(
                ids=ids[start : start + _DELETE_BATCH], namespace=namespace
            )
        return len(ids)

    async def search(
        self, vector: list[float], top_k: int = 5, namespace: str = ""
    ) -> list[SearchHit]:
        """Find the Chunks closest to a query vector."""
        response = await self._index.query(
            vector=vector, top_k=top_k, namespace=namespace, include_metadata=True
        )
        return [
            SearchHit(
                score=match.score,
                source=(match.metadata or {}).get("source", ""),
                chunk=Chunk(
                    text=(match.metadata or {}).get("chunk_text", ""),
                    headings=(match.metadata or {}).get("headings", []) or [],
                ),
            )
            for match in response.matches
        ]
