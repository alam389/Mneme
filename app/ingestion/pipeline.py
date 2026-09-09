"""Coordinate conversion, embedding, and vector storage for one ingestion request."""

import asyncio
import hashlib
import logging
from pathlib import Path

from pinecone import AsyncIndex

from app.ingestion.conversion import IngestionService
from app.ingestion.embedding_model import embed
from app.ingestion.vector_tools import VectorUpserter
from app.models.schemas import ConvertedDocument, IngestionRequest, IngestionResponse
from app.services.llm import LLMConfigError
from app.services.vector_store import VectorStoreConfigError

logger = logging.getLogger(__name__)


def _namespace_for(source: str) -> str:
    """Partition vectors by the document's containing folder.

    URLs have no folder to key off of, so they fall back to the default
    (empty-string) namespace.
    """
    if "://" in source:
        return ""
    return Path(source).parent.name


class IngestionPipeline:
    def __init__(self, service: IngestionService, index: AsyncIndex) -> None:
        self._service = service
        self._upserter = VectorUpserter(index)

    async def run(self, request: IngestionRequest) -> IngestionResponse:
        documents, message = await asyncio.to_thread(self._service.process, request)

        chunked_documents = [document for document in documents if document.chunks]
        results = await asyncio.gather(
            *(self._embed_and_upsert(document) for document in chunked_documents),
            return_exceptions=True,
        )

        failed_documents = 0
        for document, result in zip(chunked_documents, results):
            if isinstance(result, (LLMConfigError, VectorStoreConfigError)):
                raise result
            if isinstance(result, Exception):
                logger.error("failed to embed/upsert %s", document.source, exc_info=result)
                failed_documents += 1

        if failed_documents:
            message += f", {failed_documents} document(s) failed to embed"

        return IngestionResponse(
            status="ok" if documents else "error",
            source=request.source,
            received_items=len(documents),
            message=message,
            documents=documents,
        )

    async def _embed_and_upsert(self, document: ConvertedDocument) -> None:
        values = await embed([chunk.text for chunk in document.chunks])

        doc_id = hashlib.sha1(document.source.encode()).hexdigest()[:16]
        vectors = [
            {
                "id": f"{doc_id}:{i}",
                "values": vector,
                "metadata": {
                    "source": document.source,
                    "chunk_text": chunk.text,
                    "headings": chunk.headings,
                },
            }
            for i, (chunk, vector) in enumerate(zip(document.chunks, values))
        ]
        await self._upserter.upsert(vectors, namespace=_namespace_for(document.source))
