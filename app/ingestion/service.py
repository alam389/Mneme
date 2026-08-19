from pathlib import Path

from docling.datamodel.base_models import FormatToExtensions, InputFormat
from docling.document_converter import DocumentConverter

from app.models.schemas import ConvertedDocument, IngestionRequest, IngestionResponse

ALLOWED_FORMATS = [
    InputFormat.PDF,
    InputFormat.DOCX,
    InputFormat.PPTX,
    InputFormat.MD,
    InputFormat.HTML,
    InputFormat.IMAGE,
]

# Extensions to pick up when the source is a directory, derived from the formats
# above so the two can never drift apart.
ALLOWED_SUFFIXES = {
    f".{ext}" for fmt in ALLOWED_FORMATS for ext in FormatToExtensions.get(fmt, [])
}


class IngestionConfigError(RuntimeError):
    """Raised when the requested source document cannot be found."""


class IngestionService:
    def __init__(self) -> None:
        self._converter = DocumentConverter(allowed_formats=ALLOWED_FORMATS)

    def _resolve(self, source: str) -> list[str]:
        """Expand a URL, file, or directory into the list of documents to convert."""
        if "://" in source:
            return [source]

        path = Path(source).expanduser()
        if path.is_file():
            return [str(path)]

        if path.is_dir():
            found = sorted(
                str(p)
                for p in path.rglob("*")
                if p.is_file() and p.suffix.lower() in ALLOWED_SUFFIXES
            )
            if not found:
                raise IngestionConfigError(f"no supported documents found in: {path}")
            return found

        raise IngestionConfigError(f"source not found: {path}")

    def process(self, payload: IngestionRequest) -> IngestionResponse:
        sources = self._resolve(payload.source)

        # raises_on_error=False so one unreadable file does not abort the batch.
        documents = [
            ConvertedDocument(
                source=str(result.input.file),
                content=result.document.export_to_markdown(),
            )
            for result in self._converter.convert_all(sources, raises_on_error=False)
            if result.document is not None
        ]

        failed = len(sources) - len(documents)
        message = f"converted {len(documents)} of {len(sources)} documents"
        if failed:
            message += f" ({failed} failed)"

        return IngestionResponse(
            status="ok" if documents else "error",
            source=payload.source,
            received_items=len(documents),
            message=message,
            documents=documents,
        )
