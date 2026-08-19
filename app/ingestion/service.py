from docling.document_converter import DocumentConverter

from app.models.schemas import IngestionRequest, IngestionResponse


class IngestionService:
    def __init__(self) -> None:
        self._converter = DocumentConverter()

    def process(self, payload: IngestionRequest) -> IngestionResponse:
        result = self._converter.convert(payload.source)
        content = result.document.export_to_markdown()
        return IngestionResponse(
            status="ok",
            source=payload.source,
            received_items=1,
            message="converted 1 document",
            content=content,
        )
