from pydantic import BaseModel, Field


class IngestionRequest(BaseModel):
    source: str = Field(..., description="Source system or provider")
    payload: dict = Field(default_factory=dict, description="Payload to ingest")


class ConvertedDocument(BaseModel):
    source: str = Field(..., description="Path or URL this document came from")
    content: str = Field(default="", description="Extracted document content as Markdown")


class IngestionResponse(BaseModel):
    status: str
    source: str
    received_items: int
    message: str
    documents: list[ConvertedDocument] = Field(
        default_factory=list, description="One entry per converted document"
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
