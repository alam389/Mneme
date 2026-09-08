from pathlib import Path

from docling.datamodel.base_models import FormatToExtensions, InputFormat
from docling.datamodel.pipeline_options import EasyOcrOptions, ThreadedPdfPipelineOptions
from docling.document_converter import (
    DocumentConverter,
    ImageFormatOption,
    PdfFormatOption,
)

from app.ingestion.chunking import DocumentChunker
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


# Docling picks an OCR engine automatically, and the one it lands on defaults to a
# Chinese recognition model, which garbles English text. Name the engine and the
# language explicitly so that cannot happen.
PIPELINE_OPTIONS = ThreadedPdfPipelineOptions(
    ocr_options=EasyOcrOptions(lang=["en"]),
)


class IngestionService:
    def __init__(self) -> None:
        # PDFs and images run the same pipeline but need separate entries because
        # they use different backends; they share one options object.
        self._converter = DocumentConverter(
            allowed_formats=ALLOWED_FORMATS,
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=PIPELINE_OPTIONS),
                InputFormat.IMAGE: ImageFormatOption(pipeline_options=PIPELINE_OPTIONS),
            },
        )
        self._chunker = DocumentChunker()

    def resolve(self, source: str) -> list[str]:
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
        sources = self.resolve(payload.source)

        # raises_on_error=False so one unreadable file does not abort the batch.
        documents = [
            ConvertedDocument(
                source=str(result.input.file),
                chunks=self._chunker.chunk(result.document),
            )
            for result in self._converter.convert_all(sources, raises_on_error=False)
            if result.document is not None
        ]

        failed = len(sources) - len(documents)
        total_chunks = sum(len(doc.chunks) for doc in documents)
        message = (
            f"converted {len(documents)} of {len(sources)} documents "
            f"into {total_chunks} chunks"
        )
        if failed:
            message += f" ({failed} failed)"

        return documents, message
