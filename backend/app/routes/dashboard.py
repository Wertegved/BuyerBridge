from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.buyer import Buyer
from app.models.email import Email
from app.models.search import Search as SearchRecord
from app.models.user import User
from app.routes.buyers import get_buyers_for_user
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api")


@router.delete("/dashboard/data")
async def clear_dashboard_data(
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
):
    buyer_ids = {buyer.id for buyer in get_buyers_for_user(database, current_user.id)}

    deleted_emails = database.execute(
        delete(Email).where(Email.user_id == current_user.id)
    ).rowcount or 0
    deleted_buyers = 0
    if buyer_ids:
        deleted_buyers = database.execute(
            delete(Buyer).where(Buyer.id.in_(buyer_ids))
        ).rowcount or 0
    deleted_searches = database.execute(
        delete(SearchRecord).where(SearchRecord.user_id == current_user.id)
    ).rowcount or 0
    database.commit()

    return {
        "status": "ok",
        "deleted": {
            "searches": deleted_searches,
            "buyers": deleted_buyers,
            "emails": deleted_emails,
        },
    }


@router.get("/search-history")
async def get_search_history(
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
):
    searches = database.execute(
        select(SearchRecord).where(SearchRecord.user_id == current_user.id).order_by(SearchRecord.created_at.desc())
    ).scalars().all()
    return {"searches": [{
        "id": item.id,
        "product_category": item.product_category,
        "product_description": item.product_description,
        "buyer_type": item.buyer_type,
        "location": item.location,
        "country": item.country,
        "result_count": item.result_count,
        "created_at": item.created_at.isoformat(),
    } for item in searches]}


@router.get("/email-history")
async def get_email_history(
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
):
    emails = database.execute(
        select(Email).where(Email.user_id == current_user.id).order_by(Email.created_at.desc())
    ).scalars().all()
    return {"emails": [{
        "id": item.id,
        "subject": item.subject,
        "status": item.status,
        "sent_at": item.sent_at.isoformat() if item.sent_at else None,
        "created_at": item.created_at.isoformat(),
    } for item in emails]}


@router.get("/dashboard")
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
):
    searches = database.execute(
        select(SearchRecord).where(SearchRecord.user_id == current_user.id)
    ).scalars().all()
    emails = database.execute(
        select(Email).where(Email.user_id == current_user.id)
    ).scalars().all()
    recent_searches = [
        {
            "location": item.location,
            "buyer_type": item.buyer_type,
            "result_count": item.result_count,
            "created_at": item.created_at.isoformat(),
        }
        for item in sorted(searches, key=lambda item: item.created_at, reverse=True)[:5]
    ]
    recent_outreach = [
        {
            "subject": item.subject,
            "status": item.status,
            "created_at": item.created_at.isoformat(),
        }
        for item in sorted(emails, key=lambda item: item.created_at, reverse=True)[:5]
    ]
    return {
        "total_leads": sum(item.result_count for item in searches),
        "emails_sent": sum(1 for item in emails if item.status == "sent"),
        "searches": len(searches),
        "recent_searches": recent_searches,
        "recent_outreach": recent_outreach,
    }
