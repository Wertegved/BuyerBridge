from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/buyers")
async def list_buyers():
    return {"buyers": []}


@router.get("/buyers/{buyer_id}")
async def get_buyer(buyer_id: str):
    return {"buyer_id": buyer_id, "business_name": "Buyer profile will appear here after provider integration."}
