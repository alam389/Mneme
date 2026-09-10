"""Tests for the HTTP entrypoint.

The route layer should be thin: these assert it hands off to the Ingestor and
translates errors, not that ingestion works -- that is test_ingestor.py.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.routes import get_ingestor
from app.ingestion.conversion import IngestionConfigError
from app.ingestion.ingestor import Ingestor
from app.ingestion.jobs import InMemoryJobStore
from app.main import app
from app.models.schemas import JobState

from tests.conftest import FakeConverter, FakeEmbedder, FakeVectorStore, document


def _raise_missing(source: str):
    raise IngestionConfigError(f"source not found: {source}")


@pytest.fixture
def documents():
    return [document("/notes/a.pdf", "one", "two")]


@pytest.fixture
def ingestor(documents):
    return Ingestor(
        FakeEmbedder(),
        FakeVectorStore(),
        InMemoryJobStore(),
        converter=FakeConverter(documents),
    )


@pytest.fixture
def client(ingestor):
    app.dependency_overrides[get_ingestor] = lambda: ingestor
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_needs_no_providers(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_ingest_returns_202_with_a_job_id(client):
    response = client.post("/api/ingest", json={"source": "/notes", "payload": {}})

    assert response.status_code == 202
    assert response.json()["job_id"]


def test_submitted_job_is_resolvable_by_its_id(client):
    job_id = client.post("/api/ingest", json={"source": "/notes"}).json()["job_id"]

    response = client.get(f"/api/jobs/{job_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == job_id
    assert body["state"] in {s.value for s in JobState}


def test_preview_returns_chunks_and_stores_nothing(client, ingestor):
    response = client.post("/api/preview", json={"source": "/notes"})

    assert response.status_code == 200
    body = response.json()
    assert [c["text"] for c in body["documents"][0]["chunks"]] == ["one", "two"]
    assert ingestor._store.stored == {}


def test_unreadable_source_is_a_400_not_a_500(client, documents):
    converter = FakeConverter(documents)
    # IngestionConfigError is what conversion raises for a Source it cannot read.
    converter.resolve = _raise_missing
    app.dependency_overrides[get_ingestor] = lambda: Ingestor(
        FakeEmbedder(), FakeVectorStore(), InMemoryJobStore(), converter=converter
    )

    response = client.post("/api/ingest", json={"source": "/nope"})

    assert response.status_code == 400
    assert "source not found" in response.json()["detail"]


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/nope").status_code == 404


def test_missing_provider_is_503_not_500():
    app.dependency_overrides.clear()
    with TestClient(app, raise_server_exceptions=False) as raw:
        # No Ingestor on app.state means Pinecone was never configured.
        raw.app.state.ingestor = None
        response = raw.post("/api/ingest", json={"source": "/notes"})
    assert response.status_code == 503
    assert "PINECONE" in response.json()["detail"]
