# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
source .venv/bin/activate           # Python 3.11 venv, already created
pip install -r requirements.txt
uvicorn app.main:app --reload       # http://127.0.0.1:8000 — docs at /docs

python -m app.ingestion --source demo --payload '{"id": 1}'   # run ingestion without the server
```

There is no test suite, linter, or formatter configured yet. `requirements.txt` is the only dependency manifest (no lock file, no pyproject).

Endpoints are mounted under `settings.api_prefix` (default `/api`), so the real paths are `/api/health`, `/api/ingest`, `/api/prompt`. Only `/` is unprefixed.

## Architecture

FastAPI ingestion scaffold. Layering is `app/api/routes.py` → `app/ingestion/` + `app/services/*` → external providers, with `app/models/schemas.py` holding every request/response Pydantic model. `app/services/` holds the external-provider clients; the pipeline itself lives in `app/ingestion/`.

**Config** — `app/config.py` defines a single `Settings` (pydantic-settings) loaded from `.env`, exported as the module-level `settings` singleton that every other module imports directly. `extra="ignore"` means unknown `.env` keys are silently dropped — adding a variable to `.env` does nothing until a matching field is declared on `Settings` (e.g. `EMBEDDING_MODEL_NAME` is currently in `.env` but has no field, so it is inert).

**Two external providers, two lifecycle patterns:**

- **OpenRouter** (`app/services/llm.py`) — an `AsyncOpenAI` client pointed at OpenRouter's base URL, built lazily via `@lru_cache` on first call. Model ids are OpenRouter-style (`openai/gpt-4o-mini`).
- **Pinecone** (`app/services/vector_store.py`) — one `AsyncPinecone` client + index held for the whole process, opened in the `lifespan` in `app/main.py` and stashed on `app.state.vector_index`. Both objects own HTTP connection pools and must be closed, so never open one per request; read it through the `get_vector_index` FastAPI dependency. Nothing here computes embeddings — Pinecone is storage/retrieval only.

**Missing-credential convention:** unconfigured providers do not stop the app from booting. Each service raises its own config error at use time (`LLMConfigError`, `VectorStoreConfigError`); `lifespan` logs a warning and leaves `vector_index` as `None`, and routes translate the error into an HTTP 503 (see the `/prompt` handler). Follow this pattern rather than validating credentials at import.

**Ingestion package** — `app/ingestion/` has two entrypoints onto one `IngestionService` (`conversion.py`): the `/api/ingest` route, which instantiates it once at module scope in `routes.py`, and `__main__.py`, a CLI run as `python -m app.ingestion` that takes a payload from `--payload`, `--file`, or stdin and prints the response as JSON (exit 2 on bad input). Keep new pipeline logic in `app/ingestion/` so both entrypoints stay in sync — `__main__.py` should only ever do argument parsing and I/O.

`IngestionService` is still a stub — it counts payloads and echoes them back; there is no real pipeline yet, and it does not touch Pinecone or OpenRouter.

## Postman

`postman/` holds `collections/`, `environments/`, `mocks/`, `specs/` directories, all currently empty (untracked by git). The Postman MCP tools are available in this session for generating collections/specs against the API.
