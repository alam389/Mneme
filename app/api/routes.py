from fastapi import APIRouter

from app.models.schemas import IngestionRequest, IngestionResponse
from app.services.ingestion import IngestionService

router = APIRouter()
service = IngestionService()


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/ingest", response_model=IngestionResponse)
def ingest(payload: IngestionRequest) -> IngestionResponse:
    return service.process(payload)
