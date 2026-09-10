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
> storage path works end to end. The knowledge graph is wired for connections
> but not yet populated, and webhooks are not built. See
> [Roadmap](#roadmap) and [Known gaps](#known-gaps).

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
  vector_tools.py    Pinecone upsert, namespaced by containing folder
```

`pipeline.py` coordinates those steps for a single ingestion request. Documents
are embedded and upserted concurrently, and one unreadable file does not abort
the batch.

### Layering

```
app/
├── main.py                  FastAPI app + lifespan (owns provider connections)
├── mcp_server.py            MCP server entrypoint (stdio transport)
├── config.py                Settings singleton, loaded from .env
├── api/routes.py            HTTP routes
├── models/schemas.py        every request/response Pydantic model
├── ingestion/               the pipeline itself
│   ├── conversion.py        source resolution + Docling conversion
│   ├── chunking.py          heading-aware chunking
│   ├── embedding_model.py   embeddings via OpenRouter
│   ├── pipeline.py          orchestrates convert → embed → upsert
│   ├── vector_tools.py      Pinecone upsert / fetch / query
│   ├── graph_tools.py       Neo4j entity + relationship upserts
│   └── __main__.py          CLI entrypoint (argument parsing and I/O only)
└── services/                external-provider clients
    ├── llm.py               OpenRouter (AsyncOpenAI)
    ├── vector_store.py      Pinecone
    └── graph_store.py       Neo4j
```

Rule of thumb: pipeline logic lives in `app/ingestion/` so all three entrypoints
stay in sync. `__main__.py` only parses arguments and prints output.

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

Routes are mounted under `API_PREFIX` (default `/api`), so the real paths are
`/api/health`, `/api/ingest`, and `/api/prompt`. Only `/` is unprefixed.

```bash
curl -X POST http://127.0.0.1:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"source": "/path/to/notes", "payload": {}}'

curl -X POST http://127.0.0.1:8000/api/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Summarise what you know about project Mneme."}'
```

### Run ingestion without the server

Handy for iterating on the pipeline without booting uvicorn:

```bash
python -m app.ingestion --source /path/to/notes
python -m app.ingestion --source https://example.com/paper.pdf
python -m app.ingestion --source ~/docs --format text --limit 3
```

`--format text` prints a readable per-chunk listing with heading trails, which is
the fastest way to eyeball chunking quality. Exit code `2` means bad input or a
missing provider credential.

### Run the MCP server

```bash
python -m app.mcp_server                                            # stdio transport
claude mcp add mneme -- $(pwd)/.venv/bin/python -m app.mcp_server   # register with Claude Code
```

Three tools are exposed, calling straight into the same services:

| Tool | Does |
| --- | --- |
| `ingest_source` | convert, chunk, embed, and upsert a file, folder, or URL |
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
- **Fast ack, async work** — respond 202 immediately and hand the job to a
  background queue; providers time out and retry aggressively, and conversion
  plus embedding is far too slow to do inline.
- **Idempotency and replay protection** — dedupe on the provider's event id and
  reject stale timestamps, so a provider's retry does not double-ingest.
- **Incremental re-ingest** — delete the document's existing vectors by its id
  prefix before upserting the new ones, so an edited document does not
  accumulate stale chunks.

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

- A `/api/search` route mirroring the MCP `search_notes` tool.
- A real RAG endpoint: retrieve, assemble context, answer with citations back to
  the source document and heading trail.
- Reranking, and hybrid dense + keyword search.

### Operational

- A test suite — there is none today, which is the biggest gap.
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

- **`/api/ingest` does not embed or upsert.** The route calls `IngestionService`
  directly rather than `IngestionPipeline`, so the HTTP path converts and chunks
  but never reaches Pinecone. The CLI and the MCP server both use the full
  pipeline. See `app/api/routes.py`.
- **`IngestionService.process` returns a tuple**, not the `IngestionResponse` its
  annotation claims — `pipeline.py` unpacks it as `(documents, message)`, but the
  route returns it straight to FastAPI. These two need reconciling.
- **`GraphUpserter` is unwired.** No ingestion stage, route, or MCP tool calls
  it, so no entities are ever written.
- **`EMBEDDING_MODEL_NAME` in `.env` is inert** — no matching field on `Settings`.
  The embedding model is hardcoded as `baai/bge-m3` in
  `app/ingestion/embedding_model.py`.
- **No tests, linter, or formatter** are configured.

---

## License

Not yet specified.
