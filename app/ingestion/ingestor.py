"""Ingestion, end to end.

The one public way into the pipeline. Callers -- the API, the CLI, the MCP
server, and the planned webhook receiver -- learn this interface and nothing
else: resolving a Source, converting it, chunking, embedding, and upserting are
all implementation.

Two ways in:

* ``preview`` converts and chunks without embedding or storing. Synchronous and
  cheap, for inspecting chunking quality.
* ``submit`` starts an Ingestion and hands back a Job Id. ``ingest`` is
  ``submit`` followed by ``wait`` for callers that can afford to block.
"""

import asyncio
import logging
from functools import lru_cache

from app.ingestion.conversion import IngestionService
from app.ingestion.jobs import InMemoryJobStore, JobStore
from app.ingestion.ports import Embedder, VectorStore
from app.models.schemas import (
    ConvertedDocument,
    DocumentOutcome,
    IngestionRequest,
    IngestionResponse,
    IngestionResult,
    Job,
)
from app.services.llm import LLMConfigError
from app.services.vector_store import VectorStoreConfigError

logger = logging.getLogger(__name__)

# Config errors mean the process is misconfigured, not that one Document is
# bad, so they fail the whole Job instead of being recorded per Document.
FATAL_ERRORS = (LLMConfigError, VectorStoreConfigError)


@lru_cache
def _shared_converter() -> IngestionService:
    """One Docling converter per process -- building one is expensive."""
    return IngestionService()


class Ingestor:
    def __init__(
        self,
        embedder: Embedder | None,
        store: VectorStore | None,
        jobs: JobStore | None = None,
        *,
        converter: IngestionService | None = None,
    ) -> None:
        # Both are None for a preview-only Ingestor; preview touches neither.
        self._embedder = embedder
        self._store = store
        self._jobs = jobs or InMemoryJobStore()
        # Internal seam: the converter is not part of this module's interface,
        # it is substitutable only so the Ingestor's own tests stay fast.
        self._converter = converter or _shared_converter()
        # asyncio holds only weak references to tasks, so keep our own.
        self._running: set[asyncio.Task] = set()

    @classmethod
    def for_preview(cls, *, converter: IngestionService | None = None) -> "Ingestor":
        """An Ingestor that can only preview -- no Embedder, no VectorStore.

        Lets a caller inspect chunking without configuring Pinecone.
        """
        return cls(None, None, converter=converter)

    async def preview(self, request: IngestionRequest) -> IngestionResponse:
        """Convert and chunk a Source without embedding or storing anything."""
        documents, message = await asyncio.to_thread(self._converter.process, request)
        return IngestionResponse(
            status="ok" if documents else "error",
            source=request.source,
            received_items=len(documents),
            message=message,
            documents=documents,
        )

    async def submit(self, request: IngestionRequest) -> str:
        """Start an Ingestion and return its Job Id.

        Requires an Embedder and a VectorStore; a preview-only Ingestor cannot
        ingest.

        Resolving the Source happens here rather than in the Job, so an
        unreadable Source is reported to the caller instead of being buried in
        a Job that fails moments later.
        """
        if self._embedder is None or self._store is None:
            raise VectorStoreConfigError(
                "this Ingestor was built for preview only and cannot ingest"
            )
        await asyncio.to_thread(self._converter.resolve, request.source)

        job = await self._jobs.create(request.source)
        task = asyncio.create_task(self._run(job.id, request))
        self._running.add(task)
        task.add_done_callback(self._running.discard)
        return job.id

    async def ingest(self, request: IngestionRequest) -> Job:
        """Submit an Ingestion and block until it finishes."""
        job_id = await self.submit(request)
        job = await self._jobs.wait(job_id)
        assert job is not None  # the store just created it
        return job

    async def job(self, job_id: str) -> Job | None:
        """The Job as it stands now, without waiting."""
        return await self._jobs.get(job_id)

    async def wait(self, job_id: str) -> Job | None:
        """Block until the Job finishes."""
        return await self._jobs.wait(job_id)

    # -- implementation ---------------------------------------------------

    async def _run(self, job_id: str, request: IngestionRequest) -> None:
        try:
            result = await self._ingest(request)
        except Exception as exc:  # noqa: BLE001 - the Job records every failure
            logger.exception("ingestion job %s failed", job_id)
            await self._jobs.fail(job_id, str(exc))
        else:
            await self._jobs.succeed(job_id, result)

    async def _ingest(self, request: IngestionRequest) -> IngestionResult:
        documents, message = await asyncio.to_thread(self._converter.process, request)

        chunked = [document for document in documents if document.chunks]
        results = await asyncio.gather(
            *(self._store_document(document, request.replace) for document in chunked),
            return_exceptions=True,
        )

        outcomes: list[DocumentOutcome] = []
        for document, result in zip(chunked, results):
            if isinstance(result, FATAL_ERRORS):
                raise result
            if isinstance(result, Exception):
                logger.error(
                    "failed to embed/store %s", document.source, exc_info=result
                )
                outcomes.append(
                    DocumentOutcome(source=document.source, error=str(result))
                )
            else:
                outcomes.append(result)

        # Documents that converted but produced nothing to store are neither a
        # success nor a failure; record them so the counts add up.
        outcomes.extend(
            DocumentOutcome(source=document.source, chunks=0)
            for document in documents
            if not document.chunks
        )

        stored = [
            outcome
            for outcome in outcomes
            if outcome.ok and outcome.chunks and not outcome.skipped
        ]
        skipped = [outcome for outcome in outcomes if outcome.skipped]
        failed = [outcome for outcome in outcomes if not outcome.ok]
        if skipped:
            message += f", {len(skipped)} already stored"
        if failed:
            message += f", {len(failed)} document(s) failed to embed"

        return IngestionResult(
            source=request.source,
            converted=len(documents),
            stored=len(stored),
            skipped=len(skipped),
            total_chunks=sum(outcome.chunks for outcome in stored),
            documents=outcomes,
            message=message,
        )

    async def _store_document(
        self, document: ConvertedDocument, replace: bool
    ) -> DocumentOutcome:
        """Embed and store one Document, unless it is already stored.

        The check happens before embedding, so a Document that is already
        stored costs nothing rather than being re-embedded and overwritten.
        """
        already = await self._store.stored_chunks(document.source)
        if already and not replace:
            return DocumentOutcome(
                source=document.source, chunks=already, skipped=True
            )

        if already:
            # The Document may have shrunk; clear it so no Chunk outlives it.
            await self._store.forget(document.source)

        vectors = await self._embedder.embed([chunk.text for chunk in document.chunks])
        await self._store.store(document, vectors)
        return DocumentOutcome(source=document.source, chunks=len(document.chunks))
