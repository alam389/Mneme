"""Test adapters for the Ingestor's seams.

Each seam has exactly two adapters -- the production one and the fake here --
which is what justifies it existing.
"""

import pytest

from app.models.schemas import Chunk, ConvertedDocument, IngestionRequest


class FakeEmbedder:
    """Deterministic Embedder: no network, vectors derived from text length."""

    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.fail_on = fail_on or set()
        self.batches: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        for text in texts:
            if text in self.fail_on:
                raise RuntimeError(f"embedding refused: {text}")
        self.batches.append(texts)
        return [[float(len(text)), 0.5] for text in texts]


class FakeVectorStore:
    """Holds stored Chunks per Source.

    Deliberately knows nothing about ids, namespaces, or metadata -- those are
    the Pinecone adapter's secret, and a test that asserted on them would be
    testing past the seam.
    """

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.stored: dict[str, list[list[float]]] = {}
        self.forgotten: list[str] = []

    async def store(self, document, vectors: list[list[float]]) -> None:
        if self.fail:
            raise RuntimeError("vector store unavailable")
        self.stored[document.source] = list(vectors)

    async def stored_chunks(self, source: str) -> int:
        return len(self.stored.get(source, []))

    async def forget(self, source: str) -> int:
        count = len(self.stored.pop(source, []))
        self.forgotten.append(source)
        return count

    @property
    def sources(self) -> list[str]:
        return sorted(self.stored)

    @property
    def total_chunks(self) -> int:
        return sum(len(v) for v in self.stored.values())


class FakeConverter:
    """Stands in for Docling at the Ingestor's internal seam."""

    def __init__(self, documents: list[ConvertedDocument] | None = None) -> None:
        self.documents = documents if documents is not None else []
        self.missing: set[str] = set()

    def resolve(self, source: str) -> list[str]:
        if source in self.missing:
            raise FileNotFoundError(f"source not found: {source}")
        return [doc.source for doc in self.documents]

    def process(self, payload: IngestionRequest):
        total = sum(len(doc.chunks) for doc in self.documents)
        return (
            self.documents,
            f"converted {len(self.documents)} of {len(self.documents)} documents "
            f"into {total} chunks",
        )


def document(source: str, *chunks: str) -> ConvertedDocument:
    return ConvertedDocument(
        source=source,
        chunks=[Chunk(text=text, headings=["H"]) for text in chunks],
    )


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def store() -> FakeVectorStore:
    return FakeVectorStore()
