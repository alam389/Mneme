"""Tests for the Pinecone adapter.

The record shape -- id derivation, Namespace, metadata keys -- is asserted here
and nowhere else, because this is the only module that knows it.
"""

from types import SimpleNamespace

import pytest

from app.models.schemas import Chunk, ConvertedDocument
from app.services.vector_store import PineconeVectorStore


class FakeAsyncIndex:
    """Stands in for Pinecone's AsyncIndex."""

    def __init__(self, page_size: int = 100) -> None:
        self.records: dict[str, list[dict]] = {}
        self.deleted: list[tuple[list[str], str]] = []
        self.page_size = page_size
        self.matches: list = []

    async def upsert(self, vectors, namespace=""):
        self.records.setdefault(namespace, []).extend(vectors)

    async def delete(self, ids=None, namespace="", **kwargs):
        self.deleted.append((list(ids or []), namespace))
        kept = [r for r in self.records.get(namespace, []) if r["id"] not in set(ids)]
        self.records[namespace] = kept

    async def list_paginated(
        self, prefix=None, namespace="", pagination_token=None, **kwargs
    ):
        matching = [
            r for r in self.records.get(namespace, []) if r["id"].startswith(prefix)
        ]
        start = int(pagination_token or 0)
        page = matching[start : start + self.page_size]
        nxt = start + self.page_size
        more = nxt < len(matching)
        return SimpleNamespace(
            vectors=[SimpleNamespace(id=r["id"]) for r in page],
            pagination=SimpleNamespace(next=str(nxt)) if more else None,
        )

    async def query(self, vector, top_k=5, namespace="", include_metadata=True):
        return SimpleNamespace(matches=self.matches[:top_k])


def document(source: str, *texts: str) -> ConvertedDocument:
    return ConvertedDocument(
        source=source, chunks=[Chunk(text=t, headings=["H"]) for t in texts]
    )


@pytest.fixture
def index():
    return FakeAsyncIndex()


@pytest.fixture
def store(index):
    return PineconeVectorStore(index)


# -- record shape ---------------------------------------------------------

async def test_one_record_per_chunk(store, index):
    await store.store(document("/notes/a.pdf", "one", "two"), [[1.0], [2.0]])

    assert len(index.records["notes"]) == 2


async def test_metadata_carries_chunk_text_and_headings(store, index):
    await store.store(document("/notes/a.pdf", "hello"), [[1.0]])

    metadata = index.records["notes"][0]["metadata"]
    assert metadata == {
        "source": "/notes/a.pdf",
        "chunk_text": "hello",
        "headings": ["H"],
    }


async def test_records_are_namespaced_by_containing_folder(store, index):
    await store.store(document("/notes/work/a.pdf", "x"), [[1.0]])
    await store.store(document("/notes/recipes/b.pdf", "y"), [[2.0]])

    assert set(index.records) == {"work", "recipes"}


async def test_urls_fall_back_to_the_default_namespace(store, index):
    await store.store(document("https://example.com/p.pdf", "x"), [[1.0]])

    assert set(index.records) == {""}


async def test_ids_are_stable_across_runs(store, index):
    doc = document("/notes/a.pdf", "one", "two")
    await store.store(doc, [[1.0], [2.0]])
    first = [r["id"] for r in index.records["notes"]]

    index.records.clear()
    await store.store(doc, [[1.0], [2.0]])

    assert [r["id"] for r in index.records["notes"]] == first


async def test_ids_of_different_sources_do_not_collide(store, index):
    await store.store(document("/notes/a.pdf", "x"), [[1.0]])
    await store.store(document("/notes/b.pdf", "x"), [[1.0]])

    ids = {r["id"] for r in index.records["notes"]}
    assert len(ids) == 2


async def test_storing_a_document_with_no_chunks_writes_nothing(store, index):
    await store.store(document("/notes/empty.pdf"), [])

    assert index.records == {}


# -- stored_chunks / forget ----------------------------------------------

async def test_stored_chunks_is_zero_for_an_unseen_source(store):
    assert await store.stored_chunks("/notes/never.pdf") == 0


async def test_stored_chunks_counts_only_that_source(store):
    await store.store(document("/notes/a.pdf", "one", "two"), [[1.0], [2.0]])
    await store.store(document("/notes/b.pdf", "x"), [[3.0]])

    assert await store.stored_chunks("/notes/a.pdf") == 2


async def test_forget_removes_only_that_source(store, index):
    await store.store(document("/notes/a.pdf", "one", "two"), [[1.0], [2.0]])
    await store.store(document("/notes/b.pdf", "x"), [[3.0]])

    removed = await store.forget("/notes/a.pdf")

    assert removed == 2
    assert await store.stored_chunks("/notes/a.pdf") == 0
    assert await store.stored_chunks("/notes/b.pdf") == 1


async def test_forget_on_an_unseen_source_deletes_nothing(store, index):
    assert await store.forget("/notes/never.pdf") == 0
    assert index.deleted == []


async def test_forget_pages_through_long_listings(index):
    index.page_size = 2
    store = PineconeVectorStore(index)
    await store.store(document("/notes/a.pdf", *"abcde"), [[float(i)] for i in range(5)])

    # Five records over pages of two: the listing must not stop at the first page.
    assert await store.forget("/notes/a.pdf") == 5


async def test_re_storing_a_shrunk_document_leaves_no_orphans(store, index):
    await store.store(document("/notes/a.pdf", "one", "two", "three"), [[1.0]] * 3)
    await store.forget("/notes/a.pdf")
    await store.store(document("/notes/a.pdf", "one"), [[1.0]])

    assert await store.stored_chunks("/notes/a.pdf") == 1


# -- search ---------------------------------------------------------------

async def test_search_decodes_metadata_back_into_chunks(store, index):
    index.matches = [
        SimpleNamespace(
            id="abc:0",
            score=0.91,
            metadata={
                "source": "/notes/a.pdf",
                "chunk_text": "hello",
                "headings": ["Title", "Section"],
            },
        )
    ]

    [hit] = await store.search([1.0])

    assert hit.score == 0.91
    assert hit.source == "/notes/a.pdf"
    assert hit.chunk.text == "hello"
    assert hit.chunk.headings == ["Title", "Section"]


async def test_search_tolerates_records_missing_metadata(store, index):
    index.matches = [SimpleNamespace(id="abc:0", score=0.5, metadata=None)]

    [hit] = await store.search([1.0])

    assert hit.source == ""
    assert hit.chunk.text == ""
