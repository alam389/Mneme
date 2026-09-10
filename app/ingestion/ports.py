"""Seams the Ingestor depends on.

Each has two adapters -- production and test -- which is what makes them worth
declaring. Anything with only one adapter stays a concrete call.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """Turns Chunk text into vectors."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch, returning one vector per input, in order."""
        ...


@runtime_checkable
class VectorStore(Protocol):
    """Stores vectors under a Namespace.

    Only the shape the Ingestor needs is declared here; retrieval reads through
    the same adapter but does not go through this seam yet.
    """

    async def upsert(self, vectors: list[dict], namespace: str = "") -> None:
        ...
