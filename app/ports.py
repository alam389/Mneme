"""The application's seams.

Each has two adapters -- production and test -- which is what makes it worth
declaring; anything with only one adapter stays a concrete call. They live here
rather than under ``app/ingestion`` because ingestion is not the only crosser:
retrieval embeds a query and reads the vector store through the same two.

Production adapters are in ``app/services``; the test adapters are in
``tests/conftest.py``.
"""

from typing import Protocol, runtime_checkable

from app.models.schemas import ConvertedDocument


@runtime_checkable
class Embedder(Protocol):
    """Turns Chunk text into vectors."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch, returning one vector per input, in order."""
        ...


@runtime_checkable
class VectorStore(Protocol):
    """Stores a Document's Chunks and answers what is already stored.

    Only the write side the Ingestor needs is declared here; the adapter also
    reads, but retrieval does not cross this seam until it has a module of its
    own. Nothing about the record shape appears in this interface -- that is the
    point of it.
    """

    async def store(
        self, document: "ConvertedDocument", vectors: list[list[float]]
    ) -> None:
        """Write one Document's Chunks."""
        ...

    async def stored_chunks(self, source: str) -> int:
        """How many Chunks are stored for a Source; 0 means never ingested."""
        ...

    async def forget(self, source: str) -> int:
        """Delete every record stored for a Source, returning how many."""
        ...
