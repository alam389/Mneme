"""OpenRouter adapter for the Embedder seam."""

from app.config import settings
from app.services.llm import get_client

MODEL_NAME = "baai/bge-m3"


class OpenRouterEmbedder:
    """Production Embedder: embeds via OpenRouter's OpenAI-compatible API."""

    def __init__(self, model: str | None = None) -> None:
        self._model = model or settings.embedding_model_name or MODEL_NAME

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await get_client().embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in response.data]


async def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch with the default Embedder.

    Retained for callers that have no Embedder injected -- currently the MCP
    search tool, which keeps its own path until retrieval gets a module.
    """
    return await OpenRouterEmbedder().embed(texts)
