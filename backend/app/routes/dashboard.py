from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/search-history")
async def get_search_history():
    return {"searches": []}


@router.get("/email-history")
async def get_email_history():
    return {"emails": []}


@router.get("/dashboard")
async def get_dashboard():
    return {
        "total_leads": 0,
        "emails_sent": 0,
        "searches": 0,
        "recent_searches": [],
        "recent_outreach": [],
    }
