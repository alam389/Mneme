"""Tests for the OpenRouter Embedder adapter.

Batching is the adapter's secret, so it is asserted here and nowhere else --
callers only ever see ``embed(texts) -> one vector each, in order``.
"""

from types import SimpleNamespace

import pytest

from app.services import embedder as embedder_module
from app.services.embedder import (
    EmbedderConfigError,
    OpenRouterEmbedder,
    get_embedding_client,
)


class FakeEmbeddingsAPI:
    def __init__(self, shuffle: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.models: list[str] = []
        self.shuffle = shuffle

    async def create(self, model: str, input: list[str]):
        self.calls.append(list(input))
        self.models.append(model)
        data = [
            SimpleNamespace(index=i, embedding=[float(len(text))])
            for i, text in enumerate(input)
        ]
        if self.shuffle:
            data = list(reversed(data))
        return SimpleNamespace(data=data)


@pytest.fixture
def api(monkeypatch):
    fake = FakeEmbeddingsAPI()
    monkeypatch.setattr(
        embedder_module,
        "get_embedding_client",
        lambda: SimpleNamespace(embeddings=fake),
    )
    return fake


async def test_one_vector_per_text_in_order(api):
    vectors = await OpenRouterEmbedder().embed(["a", "bb", "ccc"])

    assert vectors == [[1.0], [2.0], [3.0]]


async def test_texts_are_batched(api):
    await OpenRouterEmbedder(batch_size=2).embed(["a", "b", "c", "d", "e"])

    # Five texts at two per request, and nothing dropped or duplicated.
    assert [len(call) for call in api.calls] == [2, 2, 1]
    assert [text for call in api.calls for text in call] == ["a", "b", "c", "d", "e"]


async def test_batching_is_invisible_at_the_interface(api):
    texts = [str(i) * (i + 1) for i in range(10)]

    batched = await OpenRouterEmbedder(batch_size=3).embed(texts)
    api.calls.clear()
    single = await OpenRouterEmbedder(batch_size=100).embed(texts)

    assert batched == single


async def test_vectors_are_ordered_by_index_not_arrival(monkeypatch):
    fake = FakeEmbeddingsAPI(shuffle=True)
    monkeypatch.setattr(
        embedder_module,
        "get_embedding_client",
        lambda: SimpleNamespace(embeddings=fake),
    )

    vectors = await OpenRouterEmbedder().embed(["a", "bb", "ccc"])

    # A misordered vector would silently mislabel a Chunk.
    assert vectors == [[1.0], [2.0], [3.0]]


async def test_empty_input_makes_no_request(api):
    assert await OpenRouterEmbedder().embed([]) == []
    assert api.calls == []


async def test_uses_the_configured_model(api):
    await OpenRouterEmbedder(model="baai/bge-m3").embed(["a"])

    assert api.models == ["baai/bge-m3"]


async def test_batch_size_below_one_is_refused():
    with pytest.raises(EmbedderConfigError):
        OpenRouterEmbedder(batch_size=0)


def test_missing_credentials_raise_at_use_time(monkeypatch):
    monkeypatch.setattr(embedder_module.settings, "embedding_api_key", "")
    monkeypatch.setattr(embedder_module.settings, "openrouter_api_key", "")
    get_embedding_client.cache_clear()

    with pytest.raises(EmbedderConfigError, match="EMBEDDING_API_KEY"):
        get_embedding_client()

    get_embedding_client.cache_clear()


def test_embedding_credentials_fall_back_to_openrouter(monkeypatch):
    monkeypatch.setattr(embedder_module.settings, "embedding_api_key", "")
    monkeypatch.setattr(embedder_module.settings, "openrouter_api_key", "sk-chat")
    monkeypatch.setattr(embedder_module.settings, "embedding_base_url", "")
    monkeypatch.setattr(
        embedder_module.settings, "openrouter_base_url", "https://openrouter.ai/api/v1"
    )
    get_embedding_client.cache_clear()

    client = get_embedding_client()

    assert client.api_key == "sk-chat"
    assert "openrouter.ai" in str(client.base_url)

    get_embedding_client.cache_clear()
