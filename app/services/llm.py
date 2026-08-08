from functools import lru_cache

from openai import AsyncOpenAI

from app.config import settings


class LLMConfigError(RuntimeError):
    """Raised when the OpenRouter client is used before a key is configured."""


@lru_cache
def get_client() -> AsyncOpenAI:
    if not settings.openrouter_api_key:
        raise LLMConfigError("OPENROUTER_API_KEY is not set")

    return AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        timeout=settings.ingestion_timeout_seconds,
        # Optional: labels this traffic in the OpenRouter dashboard.
        default_headers={"X-Title": settings.app_name},
    )


async def complete(prompt: str, model: str) -> str:
    response = await get_client().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""
