from fastapi import APIRouter, HTTPException

from app.config import settings
from app.models.schemas import (
    IngestionRequest,
    IngestionResponse,
    PromptRequest,
    PromptResponse,
)
from app.ingestion import IngestionService
from app.services import llm

router = APIRouter()
service = IngestionService()


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/ingest", response_model=IngestionResponse)
def ingest(payload: IngestionRequest) -> IngestionResponse:
    return service.process(payload)


@router.post("/prompt", response_model=PromptResponse)
async def prompt(request: PromptRequest) -> PromptResponse:
    model = request.model or settings.model_name
    try:
        output = await llm.complete(request.prompt, model)
    except llm.LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return PromptResponse(model=model, output=output)
