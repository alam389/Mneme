import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.api.routes import router
from app.config import settings
from app.services.embedding import open_vector_store

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Hold one Pinecone connection for the process lifetime."""
    app.state.vector_index = None

    if not (settings.pinecone_api_key and settings.pinecone_host):
        # Let the rest of the API boot; get_vector_index() reports the cause.
        logger.warning("Pinecone is not configured; vector store is disabled")
        yield
        return

    async with open_vector_store() as index:
        app.state.vector_index = index
        yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="A lightweight FastAPI scaffold for an ingestion pipeline.",
    debug=settings.debug,
    lifespan=lifespan,
)

app.include_router(router, prefix=settings.api_prefix)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "ok"}
