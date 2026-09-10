from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Mneme"
    environment: str = "development"
    debug: bool = False
    api_prefix: str = "/api"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    model_name: str = "openai/gpt-4o-mini"
    embedding_model_name: str = "baai/bge-m3"
    ingestion_timeout_seconds: int = 30
    ingestion_doc_source: str = "/Users/anthonylam"
    default_source: str = ""
    hf_token: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    pinecone_api_key: str = ""
    pinecone_host: str = ""

    neo4j_uri: str = ""
    neo4j_username: str = ""
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"



@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

__all__ = ["Settings", "get_settings", "settings"]
