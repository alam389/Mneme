"""Neo4j graph-store client.

Neo4j holds the knowledge graph (entities and relationships) built during
ingestion. This module only manages the driver connection; nothing here
extracts entities or runs domain queries — see app.ingestion.graph_tools.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Request
from neo4j import AsyncDriver, AsyncGraphDatabase

from app.config import settings


class GraphStoreConfigError(RuntimeError):
    """Raised when the Neo4j driver is used before it is configured."""


@asynccontextmanager
async def open_graph_store() -> AsyncGenerator[AsyncDriver, None]:
    """Open a Neo4j driver, closing it on exit.

    The driver owns a connection pool, so it must be closed rather than left
    to the garbage collector. Intended to be driven once from the app
    lifespan, not per request.
    """
    if not settings.neo4j_uri:
        raise GraphStoreConfigError("NEO4J_URI is not set")
    if not settings.neo4j_username:
        raise GraphStoreConfigError("NEO4J_USERNAME is not set")
    if not settings.neo4j_password:
        raise GraphStoreConfigError("NEO4J_PASSWORD is not set")

    async with AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    ) as driver:
        yield driver


def get_graph_driver(request: Request) -> AsyncDriver:
    """FastAPI dependency returning the driver opened at startup."""
    driver = getattr(request.app.state, "graph_driver", None)
    if driver is None:
        raise GraphStoreConfigError(
            "Neo4j driver is unavailable; check NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD"
        )
    return driver
