from app.models.schemas import IngestionRequest, IngestionResponse


class IngestionService:
    def process(self, payload: IngestionRequest) -> IngestionResponse:
        item_count = 1 if payload.payload else 0
        return IngestionResponse(
            status="accepted",
            source=payload.source,
            received_items=item_count,
            message="Ingestion request accepted",
        )
