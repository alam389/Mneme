"""MCP server exposing ingestion, LLM, and vector-search tools.

Run with ``python -m app.mcp_server`` (stdio transport) and register it with
a client, e.g. ``claude mcp add mneme -- python -m app.mcp_server`` from the
project's venv. Holds one Pinecone connection and one Neo4j driver for the
process lifetime, the same pattern ``app.main`` uses for the HTTP server.
"""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass

from mcp.server.mcpserver import Context, MCPServer
from neo4j import AsyncDriver
from pinecone import AsyncIndex

from app.config import settings
from app.ingestion.embedding_model import OpenRouterEmbedder, embed
from app.ingestion.ingestor import Ingestor
from app.models.schemas import IngestionRequest
from app.services.graph_store import open_graph_store
from app.services.llm import complete
from app.services.pinecone import open_vector_store
from app.services.vector_store import PineconeVectorStore, VectorStoreConfigError

logger = logging.getLogger(__name__)


@dataclass
class ServerContext:
    index: AsyncIndex | None
    graph_driver: AsyncDriver | None
    # One Ingestor for the process, so its Job store outlives a single tool call.
    ingestor: Ingestor | None


@asynccontextmanager
async def lifespan(server: MCPServer) -> AsyncIterator[ServerContext]:
    async with AsyncExitStack() as stack:
        index = None
        if settings.pinecone_api_key and settings.pinecone_host:
            index = await stack.enter_async_context(open_vector_store())
        else:
            logger.warning("Pinecone is not configured; ingest_source and search_notes will error")

        graph_driver = None
        if settings.neo4j_uri and settings.neo4j_username and settings.neo4j_password:
            graph_driver = await stack.enter_async_context(open_graph_store())
        else:
            logger.warning("Neo4j is not configured; graph tools will error")

        ingestor = (
            Ingestor(OpenRouterEmbedder(), PineconeVectorStore(index))
            if index is not None
            else None
        )

        yield ServerContext(
            index=index, graph_driver=graph_driver, ingestor=ingestor
        )


mcp = MCPServer("mneme", lifespan=lifespan)


def _index(ctx: Context) -> AsyncIndex:
    index = ctx.request_context.lifespan_context.index
    if index is None:
        raise VectorStoreConfigError(
            "Pinecone index is unavailable; check PINECONE_API_KEY and PINECONE_HOST"
        )
    return index


def _ingestor(ctx: Context) -> Ingestor:
    ingestor = ctx.request_context.lifespan_context.ingestor
    if ingestor is None:
        raise VectorStoreConfigError(
            "Ingestion is unavailable; check PINECONE_API_KEY and PINECONE_HOST"
        )
    return ingestor


@mcp.tool()
async def ingest_source(
    ctx: Context,
    source: str,
    payload: dict | None = None,
    replace: bool = False,
) -> str:
    """Convert, chunk, embed, and upsert a file, directory, or URL into the vector store.

    Documents that are already stored are skipped rather than re-embedded; pass
    replace=True when their content has actually changed.

    Blocks until the Ingestion finishes and returns a summary: counts per
    document, plus any that were skipped or failed.
    """
    request = IngestionRequest(source=source, payload=payload or {}, replace=replace)
    job = await _ingestor(ctx).ingest(request)
    if job.result is None:
        return json.dumps({"state": job.state.value, "error": job.error})
    return job.result.model_dump_json()


@mcp.tool()
async def preview_source(ctx: Context, source: str) -> str:
    """Convert and chunk a file, directory, or URL without embedding or storing it.

    Use this to check how a document will be split before paying to embed it.
    """
    request = IngestionRequest(source=source, payload={})
    response = await _ingestor(ctx).preview(request)
    return response.model_dump_json()


@mcp.tool()
async def ask_llm(prompt: str, model: str | None = None) -> str:
    """Send a prompt directly to the configured LLM via OpenRouter and return its reply."""
    return await complete(prompt, model or settings.model_name)


@mcp.tool()
async def search_notes(ctx: Context, query: str, top_k: int = 5, namespace: str = "") -> str:
    """Search previously ingested notes for chunks relevant to a query."""
    [vector] = await embed([query])
    hits = await PineconeVectorStore(_index(ctx)).search(
        vector, top_k=top_k, namespace=namespace
    )
    return json.dumps([hit.model_dump() for hit in hits], indent=2)


if __name__ == "__main__":
    mcp.run()
