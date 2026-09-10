# Mneme

Mneme turns documents into a queryable memory. This context covers how a
**Source** becomes searchable **Chunks**, and the vocabulary the ingestion and
retrieval modules share.

## Language

### Documents

**Source**:
A location Mneme is pointed at — a file path, a directory, or a URL. One Source
expands into one or more Documents.
_Avoid_: input, target, file (a Source is often a directory, not a file)

**Document**:
One converted file, carrying the Chunks it was split into. Documents are what
Docling produces; Mneme never stores the original file.
_Avoid_: doc, item, record

**Chunk**:
A retrieval-sized span of a Document, prefixed with the heading trail it sits
under so it stays meaningful once embedded. The unit that gets embedded and
stored.
_Avoid_: passage, segment, fragment, span

**Namespace**:
The partition a Document's vectors are written into, derived from its containing
folder. URLs have no folder and fall back to the default namespace.
_Avoid_: collection, partition, bucket

### Ingestion

**Ingestion**:
The whole path from Source to stored vectors: resolve, convert, chunk, embed,
upsert. Use the bare noun for the concept, never for a specific module.
_Avoid_: indexing, importing, processing

**Ingestor**:
The module that owns Ingestion end to end. Takes an Embedder and a VectorStore;
everything between Source and upsert is its implementation.
_Avoid_: IngestionService, IngestionPipeline (both are pre-existing names for
partial paths — see Flagged ambiguities), handler, manager

**Preview**:
Converting and chunking a Source without embedding or storing it. Synchronous
and cheap, so chunking quality can be inspected without paying to embed.
_Avoid_: dry run, test mode, parse-only

**Ingestion Job**:
One submitted Ingestion, identified by a Job Id and resolvable to a summary once
finished. Exists because a folder Ingestion runs for minutes, longer than an
HTTP caller or a webhook provider will wait.
_Avoid_: task, run, batch

**Job Id**:
The handle returned when an Ingestion is submitted. Callers hold it to await or
poll the result.
_Avoid_: ticket, token, handle

### Seams

**Embedder**:
The seam that turns text into vectors. Two adapters: OpenRouter in production, a
deterministic one in tests.
_Avoid_: embedding model, encoder, vectorizer

**VectorStore**:
The seam that owns the vector record — id derivation, Namespace, metadata shape
— not just the transport to Pinecone. It is the only module that knows how a
Chunk becomes a stored record.
_Avoid_: vector db, index, upserter

## Flagged ambiguities

**"IngestionService" vs "IngestionPipeline"** — both names exist in the code
today and neither means Ingestion. `IngestionService` converts and chunks only;
`IngestionPipeline` adds embedding and upsert. The names do not signal which is
which, and `/api/ingest` calls the wrong one. Resolution: **Ingestor** is the
one public name; conversion stays an internal seam with no public name.

**"ingest" the verb vs `/api/ingest` the route** — the route currently performs
a Preview, not an Ingestion. Resolution: the route becomes an Ingestion
(returning a Job Id); Preview gets its own route.

## Example dialogue

**Dev:** If I point it at `~/notes`, is that one Source or forty?

**Domain expert:** One Source. It expands into forty Documents — one per file it
can convert. Each Document splits into Chunks, and the Chunks are what get
embedded.

**Dev:** And they all land in the same Namespace?

**Domain expert:** Each Document's Namespace comes from its own containing
folder, so `~/notes/recipes/x.pdf` and `~/notes/work/y.pdf` land in different
ones. One Source, several Namespaces.

**Dev:** The chunking looked wrong last time. Do I have to re-embed the whole
folder to check?

**Domain expert:** No — that's what Preview is for. It converts and chunks and
hands the Chunks straight back. Nothing is embedded, nothing is stored.

**Dev:** So when do I get an Ingestion Job?

**Domain expert:** Only when you actually ingest. Forty PDFs with OCR takes
minutes, so you get a Job Id immediately and the summary when it finishes. A
webhook can't sit and wait for that.

**Dev:** Does the summary give me the Chunks back?

**Domain expert:** Counts and failures only. Once a Chunk is stored, the
VectorStore owns it — ask retrieval for it, not the Job.
