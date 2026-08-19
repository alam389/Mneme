from pydantic import BaseModel, Field


class IngestionRequest(BaseModel):
    source: str = Field(..., description="Source system or provider")
    payload: dict = Field(default_factory=dict, description="Payload to ingest")


class IngestionResponse(BaseModel):
    status: str
    source: str
    received_items: int
    message: str
    content: str = Field(default="", description="Extracted document content as Markdown")


class PromptRequest(BaseModel):
    prompt: str = Field(..., description="Prompt to send to the model")
    model: str | None = Field(
        default=None,
        description="OpenRouter model id, e.g. 'openai/gpt-4o-mini'. Falls back to MODEL_NAME.",
    )


class PromptResponse(BaseModel):
    model: str
    output: str
