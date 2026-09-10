# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
source .venv/bin/activate           # Python 3.11 venv, already created
pip install -r requirements.txt
uvicorn app.main:app --reload       # http://127.0.0.1:8000 — docs at /docs

python -m app.ingestion --source /path/to/notes               # full ingestion, blocks until done
python -m app.ingestion --preview --format text --limit 3 --source ~/docs   # convert+chunk only

pytest                              # no network or credentials needed

python -m app.mcp_server            # stdio MCP server exposing ingest/prompt/search as tools
claude mcp add mneme -- $(pwd)/.venv/bin/python -m app.mcp_server   # register it with Claude Code
```

Tests run under `pytest` (config in `pytest.ini`, `asyncio_mode = auto`). There is no linter or formatter configured yet. `requirements.txt` is the only dependency manifest (no lock file, no pyproject).

Endpoints are mounted under `settings.api_prefix` (default `/api`): `/api/health`, `/api/preview`, `/api/ingest`, `/api/jobs/{job_id}`, `/api/prompt`. Only `/` is unprefixed.

Domain vocabulary — Source, Document, Chunk, Ingestor, Preview, Ingestion Job — is defined in `CONTEXT.md`. Use those terms rather than inventing synonyms.

## Architecture

FastAPI ingestion scaffold. Layering is `app/api/routes.py` → `app/ingestion/` + `app/services/*` → external providers, with `app/models/schemas.py` holding every request/response Pydantic model. `app/services/` holds the external-provider clients; the pipeline itself lives in `app/ingestion/`.

**`Ingestor` is the one public way into ingestion.** All three entrypoints — the `/api/ingest` route, the CLI, and the MCP server — construct an `Ingestor` and call it; none of them assembles pipeline steps itself. `app/ingestion/__init__.py` deliberately exports only `Ingestor`: conversion and chunking are its implementation, and exporting them previously let `/api/ingest` call the wrong one and skip the vector store entirely. Keep it that way when adding entrypoints (the planned webhook receiver included).

Its interface is `preview` (convert and chunk, store nothing — needs no Pinecone credentials), `submit` (start an ingestion, return a job id), `ingest` (submit then wait), and `job`/`wait` to collect the result. Ingesting a folder runs for minutes, so `/api/ingest` returns 202 and the caller polls `/api/jobs/{id}`.

**Three seams, each with two adapters** — `Embedder` and `VectorStore` in `app/ingestion/ports.py`, `JobStore` in `app/ingestion/jobs.py`. Production adapters are `OpenRouterEmbedder`, `VectorUpserter`, and `InMemoryJobStore`; the test fakes are in `tests/conftest.py`. This is why the suite needs no network. Don't add a port without a second adapter to justify it.

`IngestionService` (conversion + chunking) is an **internal seam**: `Ingestor` takes it as a keyword argument so its own tests stay fast, but it is not part of the public interface and callers must not reach for it.

**Config** — `app/config.py` defines a single `Settings` (pydantic-settings) loaded from `.env`, exported as the module-level `settings` singleton that every other module imports directly. `extra="ignore"` means unknown `.env` keys are silently dropped — adding a variable to `.env` does nothing until a matching field is declared on `Settings` (e.g. `EMBEDDING_MODEL_NAME` is currently in `.env` but has no field, so it is inert).

**Three external providers, two lifecycle patterns:**

- **OpenRouter** (`app/services/llm.py`) — an `AsyncOpenAI` client pointed at OpenRouter's base URL, built lazily via `@lru_cache` on first call. Model ids are OpenRouter-style (`openai/gpt-4o-mini`).
- **Pinecone** (`app/services/vector_store.py`) — one `AsyncPinecone` client + index held for the whole process, opened in the `lifespan` in `app/main.py` and stashed on `app.state.vector_index`. Both objects own HTTP connection pools and must be closed, so never open one per request; read it through the `get_vector_index` FastAPI dependency. Nothing here computes embeddings — Pinecone is storage/retrieval only.
- **Neo4j** (`app/services/graph_store.py`) — the knowledge-graph counterpart to Pinecone, same lifecycle shape: one `AsyncDriver` held for the whole process, opened in `lifespan` (both `app/main.py` and `app/mcp_server.py`, via `AsyncExitStack` alongside the Pinecone connection) and stashed on `app.state.graph_driver`; read it through `get_graph_driver`. `app/ingestion/graph_tools.py` (`GraphUpserter`) is the graph equivalent of `vector_tools.py`, exposing `upsert_entity`/`upsert_relationship`/`query` over Cypher — note label and relationship-type names go through `_validate_identifier` since Neo4j has no parameter syntax for them (only property values are parameterized). Currently unwired: no ingestion step or route/MCP tool calls `GraphUpserter` yet, so entities are never actually populated. Config is `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD`/`NEO4J_DATABASE` (defaults to `"neo4j"`).

**Missing-credential convention:** unconfigured providers do not stop the app from booting. Each service raises its own config error at use time (`LLMConfigError`, `VectorStoreConfigError`, `GraphStoreConfigError`); `lifespan` logs a warning and leaves the corresponding state attribute as `None`, and routes translate the error into an HTTP 503 (see the `/prompt` handler). Follow this pattern rather than validating credentials at import.

**Ingestion package** — `app/ingestion/` holds the pipeline behind `Ingestor` (see above). `__main__.py` is the CLI (`python -m app.ingestion`); it takes `--source`, `--payload`, `--preview`, `--format`, and `--limit`, and should only ever do argument parsing and I/O — all logic belongs in `Ingestor` so the entrypoints cannot drift.

**MCP server** — `app/mcp_server.py` is a third entrypoint (alongside the API route and the ingestion CLI), built on the `mcp` package's `MCPServer` (note: this is the `mcp>=2.0` API — `FastMCP` was renamed `MCPServer` in `mcp.server.mcpserver`, so v1-era examples won't import as-is). It holds one Pinecone connection for the process lifetime via the same `lifespan`/`open_vector_store` pattern as `app.main`, and exposes four tools: `ingest_source` and `preview_source` (both via `Ingestor`), `ask_llm` (`app.services.llm.complete`), and `search_notes` (embeds the query, then `VectorUpserter.query`). It builds one `Ingestor` in its lifespan so the job store outlives a single tool call. Run it with `python -m app.mcp_server` (stdio transport).

## Postman

`postman/` holds `collections/`, `environments/`, `mocks/`, `specs/` directories, all currently empty (untracked by git). The Postman MCP tools are available in this session for generating collections/specs against the API.
