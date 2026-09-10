# Mneme

Mneme turns your documents into a queryable memory.

Point it at a file, a folder, or a URL and it converts the document (PDF, DOCX,
PPTX, Markdown, HTML, images — with OCR), splits it into retrieval-sized chunks
that keep their heading context, embeds them, and stores them in a vector index.
An LLM — or you — can then ask questions against everything you have ingested.

The same pipeline is reachable three ways: an HTTP API, a command-line
entrypoint, and an MCP server that plugs straight into Claude Code and other
MCP clients.

> **Status: early scaffold.** The conversion → chunking → embedding → vector
> storage path works end to end behind one `Ingestor` interface, covered by
> tests. The knowledge graph is wired for connections but not yet populated,
> and webhooks are not built. See [Roadmap](#roadmap) and
> [Known gaps](#known-gaps).

---

## How it works

```
source (file / folder / URL)
        │
        ▼
  conversion.py      Docling → structured document (OCR pinned to English)
        │
        ▼
  chunking.py        HybridChunker → chunks carrying their heading trail
        │
        ▼
  embedding_model.py BAAI/bge-m3 via OpenRouter
        │
        ▼
  vector_store.py    ids, namespaces, metadata, upsert
```

`Ingestor` (`ingestor.py`) coordinates those steps and is the only public way
in — the API, the CLI, and the MCP server all cross the same interface.
Documents are embedded and upserted concurrently, and one unreadable file does
not abort the batch.

Two ways in:

- **`preview(request)`** converts and chunks without embedding or storing.
  Synchronous, cheap, and needs no Pinecone credentials — this is how you
  inspect chunking quality.
- **`submit(request)`** starts an ingestion and returns a **job id**. Converting
  a folder runs for minutes, longer than an HTTP caller or a webhook provider
  will wait, so the work continues after the response. `ingest(request)` is
  `submit` followed by a wait, for callers that can afford to block.

Three seams sit under it, each with a production adapter and a test adapter:
`Embedder`, `VectorStore`, and `JobStore`. That is what makes the pipeline
testable without a live network.

Documents that are already stored are **skipped** rather than re-embedded —
checked before embedding, so re-running over a folder costs one listing instead
of an embedding bill. Pass `replace` when a document's content has actually
changed: its old chunks are forgotten first, so a document that shrank leaves
nothing stale behind.

### Layering

```
app/
├── main.py                  FastAPI app + lifespan (owns provider connections)
├── mcp_server.py            MCP server entrypoint (stdio transport)
├── config.py                Settings singleton, loaded from .env
├── api/routes.py            HTTP routes
├── models/schemas.py        every request/response Pydantic model
├── ingestion/               the pipeline itself
│   ├── ingestor.py          Ingestor — the one public way in
│   ├── ports.py             Embedder and VectorStore seams
│   ├── jobs.py              JobStore seam + in-memory adapter
│   ├── conversion.py        source resolution + Docling conversion (internal)
│   ├── chunking.py          heading-aware chunking (internal)
│   ├── embedding_model.py   OpenRouter adapter for the Embedder seam
│   ├── graph_tools.py       Neo4j entity + relationship upserts
│   └── __main__.py          CLI entrypoint (argument parsing and I/O only)
└── services/                external-provider clients
    ├── llm.py               OpenRouter (AsyncOpenAI)
    ├── pinecone.py          Pinecone connection lifecycle
    ├── vector_store.py      the vector record: ids, namespaces, metadata
    └── graph_store.py       Neo4j
```

Rule of thumb: everything goes through `Ingestor`, so the entrypoints cannot
drift. `app/ingestion/__init__.py` exports only `Ingestor` — conversion and
chunking are implementation, not a second way in. `__main__.py` only parses
arguments and prints output.

Domain vocabulary — **Source**, **Document**, **Chunk**, **Preview**,
**Ingestion Job** — is defined in [CONTEXT.md](CONTEXT.md).

### Providers

| Provider | Used for | Lifecycle |
| --- | --- | --- |
| **OpenRouter** | chat completions and embeddings | lazy `AsyncOpenAI` client, `@lru_cache`d on first use |
| **Pinecone** | vector storage and retrieval | one client + index for the whole process, opened in `lifespan` |
| **Neo4j** | knowledge graph (entities, relationships) | one `AsyncDriver` for the whole process, opened in `lifespan` |

**Missing credentials never stop the app from booting.** Each service raises its
own error at use time (`LLMConfigError`, `VectorStoreConfigError`,
`GraphStoreConfigError`); the lifespan logs a warning and leaves that state
attribute `None`, and routes translate the error into an HTTP 503. Add new
providers the same way rather than validating at import.

---

## Getting started

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` in the project root:

```dotenv
APP_NAME=Mneme
ENVIRONMENT=development
DEBUG=true
API_PREFIX=/api

# OpenRouter — chat completions and embeddings
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
MODEL_NAME=openai/gpt-4o-mini

# Pinecone — vector storage
PINECONE_API_KEY=...
PINECONE_HOST=https://your-index-....pinecone.io

# Neo4j — knowledge graph (optional today)
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=...
NEO4J_DATABASE=neo4j

# Convenience
DEFAULT_SOURCE=/path/to/your/notes
INGESTION_TIMEOUT_SECONDS=30
```

> `Settings` uses `extra="ignore"`, so **a variable in `.env` does nothing until a
> matching field is declared on `Settings` in `app/config.py`.** Adding a key
> alone is silently inert.

### Run the API

```bash
uvicorn app.main:app --reload
```

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

Routes are mounted under `API_PREFIX` (default `/api`). Only `/` is unprefixed.

| Route | Does |
| --- | --- |
| `GET /api/health` | liveness; needs no providers |
| `POST /api/preview` | convert and chunk, store nothing — returns 200 with the chunks |
| `POST /api/ingest` | start an ingestion — returns 202 with a job id |
| `GET /api/jobs/{id}` | the job's state, and its summary once finished |
| `POST /api/prompt` | send a prompt to the configured model |

```bash
# See how a source would be chunked, without paying to embed it.
curl -X POST http://127.0.0.1:8000/api/preview \
  -H "Content-Type: application/json" \
  -d '{"source": "/path/to/notes"}'

# Start an ingestion, then collect the result. Already-stored documents are
# skipped; add "replace": true to re-embed them.
curl -X POST http://127.0.0.1:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"source": "/path/to/notes"}'
# => 202 {"job_id": "5f2c..."}

curl http://127.0.0.1:8000/api/jobs/5f2c...
# => {"state": "succeeded", "result": {"stored": 38, "total_chunks": 812, ...}}

curl -X POST http://127.0.0.1:8000/api/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Summarise what you know about project Mneme."}'
```

A job's summary carries counts and per-document failures, not chunk bodies —
once a chunk is stored the vector store owns it. Jobs live in memory, so they do
not survive a restart and are not visible to the MCP server process.

### Run ingestion without the server

Handy for iterating on the pipeline without booting uvicorn:

```bash
python -m app.ingestion --source /path/to/notes
python -m app.ingestion --source https://example.com/paper.pdf

# Re-embed documents that are already stored (default is to skip them).
python -m app.ingestion --replace --source /path/to/notes

# Preview: convert and chunk only. No embedding, no storage, no Pinecone needed.
python -m app.ingestion --preview --format text --limit 3 --source ~/docs
```

`--preview --format text` prints a per-chunk listing with heading trails, which
is the fastest way to eyeball chunking quality — and it costs nothing, since
nothing is embedded. Without `--preview` the CLI runs a full ingestion and
blocks until the job finishes. Exit code `2` means bad input, a missing provider
credential, or a failed job.

### Run the tests

```bash
pytest
```

Tests cross the same interface the entrypoints do. `Embedder`, `VectorStore`,
and `JobStore` each have a fake adapter in `tests/conftest.py`, so the suite
needs no network and no credentials.

### Run the MCP server

```bash
python -m app.mcp_server                                            # stdio transport
claude mcp add mneme -- $(pwd)/.venv/bin/python -m app.mcp_server   # register with Claude Code
```

Three tools are exposed, calling straight into the same services:

| Tool | Does |
| --- | --- |
| `ingest_source` | convert, chunk, embed, and store a file, folder, or URL; skips what is already stored unless `replace=True` |
| `preview_source` | convert and chunk without embedding or storing |
| `ask_llm` | send a prompt to the configured OpenRouter model |
| `search_notes` | embed a query and return the most relevant ingested chunks |

Note this targets `mcp>=2.0`, where `FastMCP` was renamed `MCPServer`
(`mcp.server.mcpserver`). v1-era examples will not import as-is.

---

## Roadmap

### Webhooks — inbound

The goal is for Mneme to keep itself current instead of waiting to be told. A
`POST /api/webhooks/{provider}` route would accept events from the tools where
documents actually live and enqueue an ingestion run for whatever changed.

Planned work:

- **Receiver route** — one endpoint per provider (Notion, Google Drive, GitHub,
  Slack, Linear), each with its own payload adapter that normalises the event
  into an `IngestionRequest`.
- **Signature verification** — HMAC verification per provider before the payload
  is trusted, with the shared secret held in `Settings` like every other
  credential. Reject unverified requests with a 401.
- ~~**Fast ack, async work**~~ — done: `/api/ingest` already responds 202 with a
  job id, so a webhook receiver only needs to call `submit` and hand back the
  same shape. Swapping the in-memory `JobStore` for a durable adapter is what
  remains.
- **Idempotency and replay protection** — dedupe on the provider's event id and
  reject stale timestamps, so a provider's retry does not double-ingest.
- ~~**Incremental re-ingest**~~ — done: `forget(source)` deletes a document's
  vectors by id prefix, and an ingestion with `replace` calls it before storing,
  so an edited document accumulates no stale chunks. A receiver just sets
  `replace` on the request.

### Webhooks — outbound

Let other systems react to Mneme instead of polling it.

- Subscriber registration (`POST /api/subscriptions`) with a target URL and an
  event filter.
- Events: `ingestion.completed`, `ingestion.failed`, `document.updated`,
  `entity.extracted`.
- Signed payloads (HMAC over the body, timestamp in the header) so receivers can
  verify the sender.
- Retry with exponential backoff and a dead-letter log for endpoints that stay
  down.

### Knowledge graph

`GraphUpserter` already speaks Cypher, but nothing calls it yet. The remaining
work is the extraction step:

- An LLM pass over each chunk to pull out entities and relationships.
- A pipeline stage that upserts them alongside the vector upsert, so a chunk's
  vector id and its graph nodes stay cross-referenced.
- Graph-aware retrieval: expand a vector hit into its neighbourhood before
  handing context to the model.

Note that Neo4j has no parameter syntax for labels or relationship types, so
`graph_tools._validate_identifier` guards every LLM-derived identifier before it
is interpolated into a query. Keep that guard on any new Cypher.

### Retrieval and querying

- A Retrieval module, then a `/api/search` route and the MCP `search_notes`
  tool both calling it.
- A real RAG endpoint: retrieve, assemble context, answer with citations back to
  the source document and heading trail.
- Reranking, and hybrid dense + keyword search.

### Operational

- Broaden the test suite: conversion, chunking, and the MCP tools are still
  uncovered.
- Linting and formatting (ruff), and a `pyproject.toml` with a lock file to
  replace the bare `requirements.txt`.
- Structured logging and per-stage ingestion metrics.
- Auth on the API; every route is currently unauthenticated.
- Dockerfile and a deployment target.
- Postman collections and an OpenAPI spec (the `postman/` directories are
  scaffolded and empty).

---

## Known gaps

Worth knowing before you build on this:

- **Jobs are in-memory.** They die on restart and are invisible across
  processes, so a job id from the API cannot be resolved by the MCP server. The
  `JobStore` seam exists so a durable adapter can replace it without touching
  `Ingestor`.
- **`GraphUpserter` is unwired.** No ingestion stage, route, or MCP tool calls
  it, so no entities are ever written.
- **Retrieval has no module.** `search_notes` calls the vector store's `search`
  directly from the MCP tool; a future `/api/search` would duplicate that call.
- **No linter or formatter** is configured. Tests exist now (`pytest`), but only
  cover ingestion and the routes.

## License

Not yet specified.
