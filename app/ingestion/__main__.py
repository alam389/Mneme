"""Run the ingestion pipeline without the API: ``python -m app.ingestion``.

The API route and this entrypoint call the same ``IngestionService``, so the
pipeline can be exercised from a shell without booting uvicorn.
"""

import argparse
import json
import sys

from pydantic import ValidationError

from app.config import settings
from app.ingestion.conversion import IngestionService
from app.models.schemas import IngestionRequest, IngestionResponse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.ingestion",
        description="Run one ingestion request against the local pipeline.",
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
        "--format",
        choices=("json", "text"),
        default="json",
        help="json for the full response, text for a readable chunk listing",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="With --format text, show only the first N chunks per document (0 = all)",
    )
    return parser


def render_text(response: IngestionResponse, limit: int = 0) -> str:
    """Readable per-chunk listing, for inspecting output by eye."""
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
            raise ValueError(f"payload must be a JSON object, got {type(payload).__name__}")
        request = IngestionRequest(source=args.source, payload=payload)
    except (json.JSONDecodeError, ValueError, ValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    response = IngestionService().process(request)
    if args.format == "text":
        print(render_text(response, args.limit))
    else:
        print(response.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
