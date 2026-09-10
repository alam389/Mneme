"""Write entities and relationships into the Neo4j graph."""

import re

from neo4j import AsyncDriver

from app.config import settings

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(name: str) -> str:
    """Guard against Cypher injection via label/relationship-type names.

    Neo4j has no parameter syntax for labels or relationship types, so
    values that may originate from LLM-extracted entities must be validated
    before being interpolated into a query string.
    """
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid graph identifier: {name!r}")
    return name

class GraphUpserter:
    def __init__(self, driver: AsyncDriver) -> None:
        self.driver = driver

    async def upsert_entity(self, entity_id: str, label: str, properties: dict) -> None:
        label = _validate_identifier(label)
        query = f"""
        MERGE (e:{label} {{id: $entity_id}})
        SET e += $properties
        """
        async with self.driver.session(database=settings.neo4j_database) as session:
            await session.run(query, entity_id=entity_id, properties=properties)

    async def upsert_relationship(
        self,
        source_id: str,
        target_id: str,
        relationship: str,
        properties: dict | None = None,
    ) -> None:
        relationship = _validate_identifier(relationship)
        query = f"""
        MATCH (a {{id: $source_id}}), (b {{id: $target_id}})
        MERGE (a)-[r:{relationship}]->(b)
        SET r += $properties
        """
        async with self.driver.session(database=settings.neo4j_database) as session:
            await session.run(
                query,
                source_id=source_id,
                target_id=target_id,
                properties=properties or {},
            )

    async def query(self, cypher: str, parameters: dict | None = None) -> list[dict]:
        async with self.driver.session(database=settings.neo4j_database) as session:
            result = await session.run(cypher, parameters or {})
            return [record.data() async for record in result]
