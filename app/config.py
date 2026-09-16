import logging
import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Mneme"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_prefix: str = "/api"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    model_name: str = "openai/gpt-4o-mini"

    # Embeddings have their own client so they can point at a different
    # provider than chat. Blank falls back to the OpenRouter values above.
    embedding_model_name: str = "baai/bge-m3"
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_timeout_seconds: int = 60
    embedding_batch_size: int = 96
    ingestion_timeout_seconds: int = 30
    # auto = ocrmac on macOS (Apple Vision, GPU-accelerated), easyocr elsewhere.
    ocr_engine: str = "auto"
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

if settings.hf_token:
    # huggingface_hub (via docling/easyocr) reads HF_TOKEN straight from the
    # process environment, not from this Settings object.
    os.environ.setdefault("HF_TOKEN", settings.hf_token)


def configure_logging() -> None:
    """Send the app's logs to the console.

    Called once by each entrypoint. Only ``app.*`` loggers get LOG_LEVEL;
    everything else stays at WARNING so Docling and the HTTP clients do not
    drown the progress lines. Output goes to stderr on purpose: the MCP server
    speaks its protocol over stdout, and a log line there would corrupt it.
    """
    logging.basicConfig(
        level=logging.WARNING,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("app").setLevel(settings.log_level.upper())


__all__ = ["Settings", "configure_logging", "get_settings", "settings"]
