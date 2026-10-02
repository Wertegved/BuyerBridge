from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.schemas.email import EmailRequest

router = APIRouter(prefix="/api")


@router.post("/email/send")
async def send_email(payload: EmailRequest):
    if not settings.EMAIL_API_KEY or not settings.EMAIL_API_BASE_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email provider is not configured yet. Add the provider credentials and implementation.",
        )

    results = []
    for buyer_id in payload.buyer_ids:
        results.append({"buyer_id": buyer_id, "status": "failed", "error": "Provider not configured yet."})

    return {"results": results}
