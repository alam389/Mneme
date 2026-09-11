"""OpenRouter adapter for the Embedder seam.

Embeddings hold their own client rather than borrowing the chat client, so the
two can point at different providers and carry different timeouts. Embedding a
folder wants a long timeout; a chat completion does not. Credentials fall back
to the OpenRouter values, so nothing needs configuring until they diverge.
"""

from functools import lru_cache

from openai import AsyncOpenAI

from app.config import settings


class EmbedderConfigError(RuntimeError):
    """Raised when the embedding client is used before a key is configured."""


@lru_cache
def get_embedding_client() -> AsyncOpenAI:
    api_key = settings.embedding_api_key or settings.openrouter_api_key
    if not api_key:
        raise EmbedderConfigError(
            "no embedding credentials: set EMBEDDING_API_KEY or OPENROUTER_API_KEY"
        )

    return AsyncOpenAI(
        api_key=api_key,
        base_url=settings.embedding_base_url or settings.openrouter_base_url,
        timeout=settings.embedding_timeout_seconds,
        # Optional: labels this traffic in the OpenRouter dashboard.
        default_headers={"X-Title": settings.app_name},
    )


class OpenRouterEmbedder:
    """Production Embedder: OpenAI-compatible embeddings, batched.

    Batching is the adapter's business, not the caller's: a long document is
    hundreds of Chunks, and providers cap how many texts one request may carry.
    ``embed`` takes any number of texts and returns one vector each, in order.
    """

    def __init__(self, model: str | None = None, batch_size: int | None = None) -> None:
        self._model = model or settings.embedding_model_name
        # `or` would let an explicit 0 fall through to the default instead of
        # being rejected.
        self._batch_size = (
            settings.embedding_batch_size if batch_size is None else batch_size
        )
        if self._batch_size < 1:
            raise EmbedderConfigError("EMBEDDING_BATCH_SIZE must be at least 1")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            response = await get_embedding_client().embeddings.create(
                model=self._model, input=batch
            )
            # The API preserves input order, but sort by index rather than
            # trust it: one misordered vector silently mislabels a Chunk.
            vectors.extend(
                item.embedding for item in sorted(response.data, key=lambda d: d.index)
            )
        return vectors
