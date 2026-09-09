"""Write chunks into the Pinecone index."""


from pinecone import AsyncIndex


class VectorUpserter:
    def __init__(self, index: AsyncIndex) -> None:
        self.index = index

    async def upsert(self, vectors: list[dict], namespace: str = "") -> None:
        await self.index.upsert(vectors=vectors, namespace=namespace)

    async def fetch_records_ids(self, ids: list[str], namespace: str = "") -> list[dict]:
        response = await self.index.fetch(ids=ids, namespace=namespace)
        return response.vectors
