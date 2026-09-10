"""MCP server exposing ingestion, LLM, and vector-search tools.

Run with ``python -m app.mcp_server`` (stdio transport) and register it with
a client, e.g. ``claude mcp add mneme -- python -m app.mcp_server`` from the
project's venv. Holds one Pinecone connection for the process lifetime, the
same pattern ``app.main`` uses for the HTTP server.
"""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.mcpserver import Context, MCPServer
from pinecone import AsyncIndex

from app.config import settings
from app.ingestion.conversion import IngestionService
from app.ingestion.embedding_model import embed
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.vector_tools import VectorUpserter
from app.models.schemas import IngestionRequest
from app.services.llm import complete
from app.services.vector_store import VectorStoreConfigError, open_vector_store

logger = logging.getLogger(__name__)


@dataclass
class ServerContext:
    index: AsyncIndex | None


@asynccontextmanager
async def lifespan(server: MCPServer) -> AsyncIterator[ServerContext]:
    if not (settings.pinecone_api_key and settings.pinecone_host):
        logger.warning("Pinecone is not configured; ingest_source and search_notes will error")
        yield ServerContext(index=None)
        return

    async with open_vector_store() as index:
        yield ServerContext(index=index)


mcp = MCPServer("mneme", lifespan=lifespan)


def _index(ctx: Context) -> AsyncIndex:
    index = ctx.request_context.lifespan_context.index
    if index is None:
        raise VectorStoreConfigError(
            "Pinecone index is unavailable; check PINECONE_API_KEY and PINECONE_HOST"
        )
    return index


@mcp.tool()
async def ingest_source(ctx: Context, source: str, payload: dict | None = None) -> str:
    """Convert, chunk, embed, and upsert a file, directory, or URL into the vector store."""
    request = IngestionRequest(source=source, payload=payload or {})
    pipeline = IngestionPipeline(IngestionService(), _index(ctx))
    response = await pipeline.run(request)
    return response.model_dump_json()


@mcp.tool()
async def ask_llm(prompt: str, model: str | None = None) -> str:
    """Send a prompt directly to the configured LLM via OpenRouter and return its reply."""
    return await complete(prompt, model or settings.model_name)


@mcp.tool()
async def search_notes(ctx: Context, query: str, top_k: int = 5, namespace: str = "") -> str:
    """Search previously ingested notes for chunks relevant to a query."""
    [vector] = await embed([query])
    matches = await VectorUpserter(_index(ctx)).query(vector, top_k=top_k, namespace=namespace)
    return json.dumps(matches, indent=2)


if __name__ == "__main__":
    mcp.run()
