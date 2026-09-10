"""Tests at the Ingestor's interface.

Everything is asserted through preview/submit/ingest -- the same surface the
API, the CLI, and the MCP server cross. Nothing reaches past it into
conversion, embedding, or storage internals.
"""

import pytest

from app.ingestion.ingestor import Ingestor
from app.ingestion.jobs import InMemoryJobStore
from app.models.schemas import IngestionRequest, JobState
from app.services.vector_store import VectorStoreConfigError

from tests.conftest import FakeConverter, FakeEmbedder, FakeVectorStore, document


def make(documents, embedder=None, store=None, converter=None):
    return Ingestor(
        embedder or FakeEmbedder(),
        store or FakeVectorStore(),
        InMemoryJobStore(),
        converter=converter or FakeConverter(documents),
    )


def request(source="/notes"):
    return IngestionRequest(source=source, payload={})


# -- preview --------------------------------------------------------------

async def test_preview_returns_chunks_without_storing(store, embedder):
    ingestor = make([document("/notes/a.pdf", "one", "two")], embedder, store)

    result = await ingestor.preview(request())

    assert result.status == "ok"
    assert [chunk.text for chunk in result.documents[0].chunks] == ["one", "two"]
    # The whole point of Preview: nothing embedded, nothing stored.
    assert embedder.batches == []
    assert store.all_records == []


async def test_preview_on_empty_source_reports_error_status():
    result = await make([]).preview(request())

    assert result.status == "error"
    assert result.documents == []


# -- ingest ---------------------------------------------------------------

async def test_ingest_stores_one_record_per_chunk(store, embedder):
    ingestor = make(
        [document("/notes/a.pdf", "one", "two"), document("/notes/b.pdf", "three")],
        embedder,
        store,
    )

    job = await ingestor.ingest(request())

    assert job.state is JobState.SUCCEEDED
    assert job.result.converted == 2
    assert job.result.stored == 2
    assert job.result.total_chunks == 3
    assert len(store.all_records) == 3


async def test_ingest_carries_chunk_text_and_headings_into_metadata(store):
    ingestor = make([document("/notes/a.pdf", "hello")], store=store)

    await ingestor.ingest(request())

    metadata = store.all_records[0]["metadata"]
    assert metadata["source"] == "/notes/a.pdf"
    assert metadata["chunk_text"] == "hello"
    assert metadata["headings"] == ["H"]


async def test_records_are_namespaced_by_containing_folder(store):
    ingestor = make(
        [document("/notes/work/a.pdf", "x"), document("/notes/recipes/b.pdf", "y")],
        store=store,
    )

    await ingestor.ingest(request())

    assert set(store.by_namespace) == {"work", "recipes"}


async def test_urls_fall_back_to_the_default_namespace(store):
    ingestor = make([document("https://example.com/p.pdf", "x")], store=store)

    await ingestor.ingest(request())

    assert set(store.by_namespace) == {""}


async def test_chunk_ids_are_stable_across_runs(store):
    for _ in range(2):
        await make([document("/notes/a.pdf", "one", "two")], store=store).ingest(
            request()
        )

    ids = [record["id"] for record in store.all_records]
    # Re-ingesting the same Source overwrites rather than accumulating.
    assert ids[:2] == ids[2:]


async def test_document_with_no_chunks_is_counted_but_not_stored(store, embedder):
    ingestor = make([document("/notes/empty.pdf")], embedder, store)

    job = await ingestor.ingest(request())

    assert job.result.converted == 1
    assert job.result.stored == 0
    assert job.result.failed == []
    assert store.all_records == []


# -- partial failure ------------------------------------------------------

async def test_one_failing_document_does_not_fail_the_job(store):
    embedder = FakeEmbedder(fail_on={"bad"})
    ingestor = make(
        [document("/notes/ok.pdf", "good"), document("/notes/bad.pdf", "bad")],
        embedder,
        store,
    )

    job = await ingestor.ingest(request())

    # The Job ran, so it succeeded; the Document that failed is reported.
    assert job.state is JobState.SUCCEEDED
    assert job.result.stored == 1
    assert [outcome.source for outcome in job.result.failed] == ["/notes/bad.pdf"]
    assert "1 document(s) failed" in job.result.message


async def test_config_error_fails_the_whole_job():
    class Unconfigured:
        async def embed(self, texts):
            raise VectorStoreConfigError("PINECONE_API_KEY is not set")

    ingestor = make([document("/notes/a.pdf", "x")], embedder=Unconfigured())

    job = await ingestor.ingest(request())

    # Misconfiguration is not a per-Document problem.
    assert job.state is JobState.FAILED
    assert "PINECONE_API_KEY" in job.error
    assert job.result is None


async def test_unreadable_source_is_reported_at_submit_not_buried_in_a_job():
    converter = FakeConverter([])
    converter.missing.add("/nope")
    ingestor = make([], converter=converter)

    with pytest.raises(FileNotFoundError):
        await ingestor.submit(request("/nope"))


# -- jobs -----------------------------------------------------------------

async def test_submit_returns_immediately_and_result_arrives_later(store):
    ingestor = make([document("/notes/a.pdf", "x")], store=store)

    job_id = await ingestor.submit(request())
    pending = await ingestor.job(job_id)
    assert pending.state is JobState.RUNNING

    finished = await ingestor.wait(job_id)
    assert finished.state is JobState.SUCCEEDED


async def test_unknown_job_id_is_none():
    assert await make([]).job("nope") is None
