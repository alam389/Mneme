import logging
from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.api.routes import router
from app.config import settings
from app.services.graph_store import open_graph_store
from app.services.vector_store import open_vector_store

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Hold one Pinecone connection and one Neo4j driver for the process lifetime."""
    app.state.vector_index = None
    app.state.graph_driver = None

    async with AsyncExitStack() as stack:
        if settings.pinecone_api_key and settings.pinecone_host:
            app.state.vector_index = await stack.enter_async_context(open_vector_store())
        else:
            # Let the rest of the API boot; get_vector_index() reports the cause.
            logger.warning("Pinecone is not configured; vector store is disabled")

        if settings.neo4j_uri and settings.neo4j_username and settings.neo4j_password:
            app.state.graph_driver = await stack.enter_async_context(open_graph_store())
        else:
            # Let the rest of the API boot; get_graph_driver() reports the cause.
            logger.warning("Neo4j is not configured; graph store is disabled")

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
