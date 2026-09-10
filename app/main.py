import logging
from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import settings
from app.ingestion.embedding_model import OpenRouterEmbedder
from app.ingestion.ingestor import Ingestor
from app.services.pinecone import open_vector_store
from app.services.vector_store import PineconeVectorStore
from app.services.graph_store import GraphStoreConfigError, open_graph_store
from app.services.llm import LLMConfigError
from app.services.vector_store import VectorStoreConfigError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Hold one Pinecone connection and one Neo4j driver for the process lifetime.

    The Ingestor is built here too, so its Job store lives as long as the
    process and a Job Id handed out by /ingest is still resolvable at /jobs.
    """
    app.state.vector_index = None
    app.state.graph_driver = None
    app.state.ingestor = None

    async with AsyncExitStack() as stack:
        if settings.pinecone_api_key and settings.pinecone_host:
            app.state.vector_index = await stack.enter_async_context(open_vector_store())
            app.state.ingestor = Ingestor(
                OpenRouterEmbedder(), PineconeVectorStore(app.state.vector_index)
            )
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
    description="Turns documents into a queryable memory.",
    debug=settings.debug,
    lifespan=lifespan,
)

app.include_router(router, prefix=settings.api_prefix)


# Unconfigured providers are a deployment problem, not a bad request: every
# service raises its own config error at use time and they all mean 503.
@app.exception_handler(LLMConfigError)
@app.exception_handler(VectorStoreConfigError)
@app.exception_handler(GraphStoreConfigError)
async def handle_config_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "ok"}
