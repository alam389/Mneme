from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Mneme"
    environment: str = "development"
    debug: bool = False
    api_prefix: str = "/api"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    model_name: str = "openai/gpt-4o-mini"
    ingestion_timeout_seconds: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )




@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

__all__ = ["Settings", "get_settings", "settings"]
