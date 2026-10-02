from __future__ import annotations

from pydantic import BaseModel, Field


class BuyerRecord(BaseModel):
    id: str | None = None
    business_name: str | None = None
    category: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    website: str | None = None
    phone: str | None = None
    email: str | None = None
    email_available: bool = False
    source: str | None = None
    contact_source: str | None = None
    relevance_score: int | None = None


class BuyerListResponse(BaseModel):
    buyers: list[BuyerRecord] = []
