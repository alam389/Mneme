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
    """Records what would have been stored, per Namespace."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.by_namespace: dict[str, list[dict]] = {}

    async def upsert(self, vectors: list[dict], namespace: str = "") -> None:
        if self.fail:
            raise RuntimeError("vector store unavailable")
        self.by_namespace.setdefault(namespace, []).extend(vectors)

    @property
    def all_records(self) -> list[dict]:
        return [rec for recs in self.by_namespace.values() for rec in recs]


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
