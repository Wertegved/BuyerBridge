from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.schemas.search import SearchRequest

router = APIRouter(prefix="/api")


@router.post("/search-buyers")
async def search_buyers(payload: SearchRequest):
    if not settings.BUSINESS_API_KEY or not settings.BUSINESS_API_BASE_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Business discovery provider is not configured yet. Add API credentials and provider implementation.",
        )

    return {
        "status": "ok",
        "message": "Provider integration is not configured yet. Add the business search provider to enable live buyer discovery.",
        "results": [],
    }
