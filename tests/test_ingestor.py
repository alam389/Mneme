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
    assert store.stored == {}


async def test_preview_on_empty_source_reports_error_status():
    result = await make([]).preview(request())

    assert result.status == "error"
    assert result.documents == []


# -- ingest ---------------------------------------------------------------

async def test_ingest_stores_every_converted_document(store, embedder):
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
    assert store.sources == ["/notes/a.pdf", "/notes/b.pdf"]
    assert store.total_chunks == 3


async def test_document_with_no_chunks_is_counted_but_not_stored(store, embedder):
    ingestor = make([document("/notes/empty.pdf")], embedder, store)

    job = await ingestor.ingest(request())

    assert job.result.converted == 1
    assert job.result.stored == 0
    assert job.result.failed == []
    assert store.stored == {}


# -- already stored -------------------------------------------------------

async def test_already_stored_document_is_skipped_without_embedding(store, embedder):
    docs = [document("/notes/a.pdf", "one", "two")]
    await make(docs, embedder, store).ingest(request())
    embedder.batches.clear()

    job = await make(docs, embedder, store).ingest(request())

    outcome = job.result.documents[0]
    assert outcome.skipped is True
    assert outcome.chunks == 2
    assert job.result.skipped == 1
    assert job.result.stored == 0
    # The point of skipping: no second embedding bill.
    assert embedder.batches == []
    assert "1 already stored" in job.result.message


async def test_replace_re_embeds_and_clears_the_old_chunks(store, embedder):
    await make([document("/notes/a.pdf", "one", "two")], embedder, store).ingest(
        request()
    )
    embedder.batches.clear()

    shrunk = [document("/notes/a.pdf", "one")]
    job = await make(shrunk, embedder, store).ingest(
        IngestionRequest(source="/notes", replace=True)
    )

    assert job.result.skipped == 0
    assert job.result.stored == 1
    assert embedder.batches == [["one"]]
    # forget() ran first, so nothing from the longer version survives.
    assert store.forgotten == ["/notes/a.pdf"]
    assert store.total_chunks == 1


async def test_a_new_document_is_not_forgotten_first(store, embedder):
    await make([document("/notes/a.pdf", "one")], embedder, store).ingest(request())

    assert store.forgotten == []


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
