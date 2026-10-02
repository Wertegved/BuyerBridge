from __future__ import annotations

from pydantic import BaseModel, Field


class EmailRequest(BaseModel):
    buyer_ids: list[str] = Field(..., min_length=1)
    subject: str = Field(..., min_length=3, max_length=200)
    message: str = Field(..., min_length=10, max_length=5000)


class EmailRecipientResult(BaseModel):
    buyer_id: str
    status: str
    error: str | None = None


class EmailSendResponse(BaseModel):
    results: list[EmailRecipientResult] = []
