"""Run an Ingestion without the API: ``python -m app.ingestion``.

Every entrypoint -- this one, the API, and the MCP server -- goes through the
same Ingestor, so this file only parses arguments and prints results.
"""

import argparse
import asyncio
import json
import sys

from pydantic import ValidationError

from app.config import settings
from app.ingestion.conversion import IngestionConfigError
from app.ingestion.embedding_model import OpenRouterEmbedder
from app.ingestion.ingestor import Ingestor
from app.services.pinecone import open_vector_store
from app.services.vector_store import PineconeVectorStore
from app.models.schemas import (
    IngestionRequest,
    IngestionResponse,
    IngestionResult,
    Job,
    JobState,
)
from app.services.llm import LLMConfigError
from app.services.vector_store import VectorStoreConfigError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.ingestion",
        description="Ingest one Source, or preview how it would be chunked.",
    )
    parser.add_argument(
        "--source",
        default=settings.default_source,
        help="Document URL or local path to ingest (defaults to DEFAULT_SOURCE)",
    )
    parser.add_argument(
        "--payload",
        default="{}",
        help="Payload as an inline JSON object",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Re-embed documents that are already stored (off by default, so "
        "re-running over a folder costs nothing)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Convert and chunk only: nothing is embedded or stored, and no "
        "Pinecone credentials are needed",
    )
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="json for the full result, text for a readable listing",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="With --preview --format text, show only the first N chunks per "
        "document (0 = all)",
    )
    return parser


def _fail(exc: Exception) -> int:
    print(f"error: {exc}", file=sys.stderr)
    return 2


def render_preview(response: IngestionResponse, limit: int = 0) -> str:
    """Readable per-chunk listing, for inspecting chunking by eye."""
    lines = [response.message, ""]
    for doc in response.documents:
        shown = doc.chunks[:limit] if limit > 0 else doc.chunks
        lines.append(f"# {doc.source} ({len(doc.chunks)} chunks)")
        for i, chunk in enumerate(shown):
            trail = " > ".join(chunk.headings) if chunk.headings else "(no heading)"
            lines.append(f"  [{i}] {trail}")
            lines.append(f"      {chunk.text[:300]}")
        if len(shown) < len(doc.chunks):
            lines.append(f"  ... {len(doc.chunks) - len(shown)} more")
        lines.append("")
    return "\n".join(lines)


def render_result(result: IngestionResult) -> str:
    """One line per Document, failures last."""
    lines = [result.message, ""]
    for outcome in result.documents:
        mark = "FAIL" if not outcome.ok else "skip" if outcome.skipped else "ok  "
        detail = outcome.error if outcome.error else f"{outcome.chunks} chunks"
        lines.append(f"  {mark} {outcome.source} — {detail}")
    lines.append("")
    summary = (
        f"stored {result.stored}/{result.converted} documents, "
        f"{result.total_chunks} chunks"
    )
    if result.skipped:
        summary += f" ({result.skipped} already stored)"
    lines.append(summary)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.source:
        print(
            "error: no source given; pass --source or set DEFAULT_SOURCE in .env",
            file=sys.stderr,
        )
        return 2

    try:
        payload = json.loads(args.payload)
        if not isinstance(payload, dict):
            raise ValueError(
                f"payload must be a JSON object, got {type(payload).__name__}"
            )
        request = IngestionRequest(
            source=args.source, payload=payload, replace=args.replace
        )
    except (json.JSONDecodeError, ValueError, ValidationError) as exc:
        return _fail(exc)

    try:
        if args.preview:
            response = asyncio.run(_preview(request))
            print(
                render_preview(response, args.limit)
                if args.format == "text"
                else response.model_dump_json(indent=2)
            )
            return 0

        job = asyncio.run(_ingest(request))
    except (VectorStoreConfigError, LLMConfigError, IngestionConfigError) as exc:
        return _fail(exc)

    if job.state is JobState.FAILED:
        return _fail(RuntimeError(job.error or "ingestion failed"))

    print(
        render_result(job.result)
        if args.format == "text"
        else job.result.model_dump_json(indent=2)
    )
    return 0


async def _preview(request: IngestionRequest) -> IngestionResponse:
    return await Ingestor.for_preview().preview(request)


async def _ingest(request: IngestionRequest) -> Job:
    async with open_vector_store() as index:
        ingestor = Ingestor(OpenRouterEmbedder(), PineconeVectorStore(index))
        return await ingestor.ingest(request)


if __name__ == "__main__":
    raise SystemExit(main())
