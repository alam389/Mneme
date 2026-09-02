from app.services.llm import get_client

MODEL_NAME = "baai/bge-m3"


async def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts with BAAI/bge-m3 via OpenRouter's OpenAI-compatible API."""
    response = await get_client().embeddings.create(model=MODEL_NAME, input=texts)
    return [item.embedding for item in response.data]
