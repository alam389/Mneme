from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.config import settings
from app.ingestion.conversion import IngestionConfigError
from app.ingestion.ingestor import Ingestor
from app.models.schemas import (
    IngestionRequest,
    IngestionResponse,
    Job,
    JobSubmission,
    PromptRequest,
    PromptResponse,
)
from app.services import llm
from app.services.vector_store import VectorStoreConfigError

router = APIRouter()


def get_ingestor(request: Request) -> Ingestor:
    """The Ingestor built at startup.

    Unconfigured providers do not stop the app booting, so the error surfaces
    here rather than at import.
    """
    ingestor = getattr(request.app.state, "ingestor", None)
    if ingestor is None:
        raise VectorStoreConfigError(
            "Ingestion is unavailable; check PINECONE_API_KEY and PINECONE_HOST"
        )
    return ingestor


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/preview", response_model=IngestionResponse)
async def preview(
    payload: IngestionRequest, ingestor: Ingestor = Depends(get_ingestor)
) -> IngestionResponse:
    """Convert and chunk a Source without embedding or storing it."""
    try:
        return await ingestor.preview(payload)
    except IngestionConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/ingest", response_model=JobSubmission, status_code=status.HTTP_202_ACCEPTED
)
async def ingest(
    payload: IngestionRequest, ingestor: Ingestor = Depends(get_ingestor)
) -> JobSubmission:
    """Start an Ingestion and return its Job Id.

    Converting a folder runs for minutes, far longer than a caller will hold a
    connection, so the work continues after this responds.
    """
    try:
        job_id = await ingestor.submit(payload)
    except IngestionConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JobSubmission(job_id=job_id)


@router.get("/jobs/{job_id}", response_model=Job)
async def read_job(job_id: str, ingestor: Ingestor = Depends(get_ingestor)) -> Job:
    job = await ingestor.job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"no such job: {job_id}")
    return job


@router.post("/prompt", response_model=PromptResponse)
async def prompt(request: PromptRequest) -> PromptResponse:
    model = request.model or settings.model_name
    try:
        output = await llm.complete(request.prompt, model)
    except llm.LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return PromptResponse(model=model, output=output)
