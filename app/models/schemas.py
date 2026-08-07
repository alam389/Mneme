from pydantic import BaseModel, Field


class IngestionRequest(BaseModel):
    source: str = Field(..., description="Source system or provider")
    payload: dict = Field(default_factory=dict, description="Payload to ingest")


class IngestionResponse(BaseModel):
    status: str
    source: str
    received_items: int
    message: str
