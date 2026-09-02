"""Pinecone vector-store client.

Pinecone is used purely for storage and retrieval of vectors. The embeddings
themselves are produced elsewhere; nothing in this module calls an embedding
model.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Request
from pinecone import AsyncIndex, AsyncPinecone

from app.config import settings


class VectorStoreConfigError(RuntimeError):
    """Raised when the Pinecone client is used before it is configured."""


@asynccontextmanager
async def open_vector_store() -> AsyncGenerator[AsyncIndex, None]:
    """Open a Pinecone client and index, releasing both on exit.

    Both objects own HTTP connection pools, so they must be closed rather than
    left to the garbage collector. Intended to be driven once from the app
    lifespan, not per request.
    """
    if not settings.pinecone_api_key:
        raise VectorStoreConfigError("PINECONE_API_KEY is not set")
    if not settings.pinecone_host:
        raise VectorStoreConfigError("PINECONE_HOST is not set")

    async with AsyncPinecone(api_key=settings.pinecone_api_key) as client:
        # index() is a coroutine, and targeting by host skips a describe_index
        # lookup on every call.
        index = await client.index(host=settings.pinecone_host)
        async with index:
            yield index


def get_vector_index(request: Request) -> AsyncIndex:
    """FastAPI dependency returning the index opened at startup."""
    index = getattr(request.app.state, "vector_index", None)
    if index is None:
        raise VectorStoreConfigError(
            "Pinecone index is unavailable; check PINECONE_API_KEY and PINECONE_HOST"
        )
    return index
