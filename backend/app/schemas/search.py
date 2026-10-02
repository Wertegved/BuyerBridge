from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    product_category: str = Field(..., min_length=2, max_length=200)
    product_description: str = Field(..., min_length=10, max_length=2000)
    buyer_type: str = Field(..., min_length=2, max_length=200)
    location: str = Field(..., min_length=2, max_length=200)
    country: str = Field(default="United States", min_length=2, max_length=200)
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("country")
    @classmethod
    def validate_country(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Country is required.")
        return value

    @field_validator("product_category", "buyer_type", "location", "product_description")
    @classmethod
    def strip_and_validate(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be empty.")
        return value


class SearchResponse(BaseModel):
    status: str = "ok"
    message: str | None = None
    results: list[dict] = []
