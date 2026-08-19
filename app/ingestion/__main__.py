"""Run the ingestion pipeline without the API: ``python -m app.ingestion``.

The API route and this entrypoint call the same ``IngestionService``, so the
pipeline can be exercised from a shell without booting uvicorn.
"""

import argparse
import json
import sys

from pydantic import ValidationError

from app.config import settings
from app.ingestion.service import IngestionService
from app.models.schemas import IngestionRequest


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
    return parser


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
    print(response.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
