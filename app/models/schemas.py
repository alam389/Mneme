from enum import Enum

from pydantic import BaseModel, Field


class IngestionRequest(BaseModel):
    source: str = Field(..., description="Source system or provider")
    payload: dict = Field(default_factory=dict, description="Payload to ingest")
    replace: bool = Field(
        default=False,
        description=(
            "Re-embed documents that are already stored. Off by default so "
            "re-running over a folder costs nothing; set it when the content "
            "has actually changed."
        ),
    )


class Chunk(BaseModel):
    text: str = Field(..., description="Chunk body, prefixed with its headings")
    headings: list[str] = Field(
        default_factory=list, description="Heading trail this chunk sits under"
    )


class ConvertedDocument(BaseModel):
    source: str = Field(..., description="Path or URL this document came from")
    chunks: list[Chunk] = Field(
        default_factory=list, description="Retrieval-sized spans of this document"
    )


class SearchHit(BaseModel):
    """One Chunk found by a search, with how well it matched."""

    score: float = Field(..., description="Similarity score from the vector store")
    source: str = Field(..., description="Document this chunk came from")
    chunk: Chunk


class IngestionResponse(BaseModel):
    """Result of a Preview: converted Documents with their Chunks, nothing stored."""

    status: str
    source: str
    received_items: int
    message: str
    documents: list[ConvertedDocument] = Field(
        default_factory=list, description="One entry per converted document"
    )


class DocumentOutcome(BaseModel):
    """What happened to one Document during an Ingestion."""

    source: str = Field(..., description="Path or URL this document came from")
    chunks: int = Field(0, description="Chunks embedded and stored, or already stored")
    skipped: bool = Field(
        default=False, description="Already stored, so it was not re-embedded"
    )
    error: str | None = Field(
        default=None, description="Why this document failed, if it did"
    )

    @property
    def ok(self) -> bool:
        return self.error is None


class IngestionResult(BaseModel):
    """Summary of a finished Ingestion.

    Carries counts and failures, not Chunk bodies: once a Chunk is stored the
    VectorStore owns it, so retrieval is where you read it back.
    """

    source: str
    converted: int = Field(0, description="Documents converted from the source")
    stored: int = Field(0, description="Documents embedded and stored")
    skipped: int = Field(0, description="Documents already stored, left untouched")
    total_chunks: int = Field(0, description="Chunks stored across all documents")
    documents: list[DocumentOutcome] = Field(default_factory=list)
    message: str = ""

    @property
    def failed(self) -> list[DocumentOutcome]:
        return [doc for doc in self.documents if not doc.ok]


class JobSubmission(BaseModel):
    """Handed back when an Ingestion is submitted."""

    job_id: str = Field(..., description="Poll /jobs/{job_id} for the result")


class JobState(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Job(BaseModel):
    """One submitted Ingestion, resolvable to a summary once finished.

    A Job succeeds when the Ingestion ran, even if individual Documents failed --
    those are reported in ``result.documents``. It fails only when the Ingestion
    itself could not run.
    """

    id: str
    source: str
    state: JobState = JobState.RUNNING
    result: IngestionResult | None = None
    error: str | None = Field(
        default=None, description="Why the ingestion could not run, if it could not"
    )


class PromptRequest(BaseModel):
    prompt: str = Field(..., description="Prompt to send to the model")
    model: str | None = Field(
        default=None,
        description="OpenRouter model id, e.g. 'openai/gpt-4o-mini'. Falls back to MODEL_NAME.",
    )


class PromptResponse(BaseModel):
    model: str
    output: str
