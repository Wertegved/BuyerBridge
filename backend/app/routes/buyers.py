from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.buyer import Buyer
from app.models.search import Search as SearchRecord
from app.models.user import User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api")


@router.get("/buyers")
async def list_buyers(
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
):
    searches = database.execute(
        select(SearchRecord).order_by(SearchRecord.created_at.asc(), SearchRecord.id.asc())
    ).scalars().all()

    buyers: list[Buyer] = []
    for index in range(len(searches) - 1, -1, -1):
        search = searches[index]
        if search.user_id != current_user.id or search.result_count <= 0:
            continue

        buyer_query = select(Buyer).where(Buyer.created_at >= search.created_at)
        if index + 1 < len(searches):
            buyer_query = buyer_query.where(Buyer.created_at < searches[index + 1].created_at)

        search_buyers = database.execute(
            buyer_query.order_by(Buyer.created_at.desc(), Buyer.id.desc()).limit(search.result_count)
        ).scalars().all()
        buyers.extend(search_buyers)

    return {
        "buyers": [
            {
                "id": str(buyer.id),
                "business_name": buyer.business_name,
                "category": buyer.category,
                "address": buyer.address,
                "city": buyer.city,
                "state": buyer.state,
                "country": buyer.country,
                "website": buyer.website,
                "phone": buyer.phone,
                "email": buyer.email,
                "email_available": buyer.email_available,
                "source": buyer.source,
                "contact_source": buyer.contact_source,
                "relevance_score": buyer.relevance_score,
            }
            for buyer in buyers
        ]
    }


@router.get("/buyers/{buyer_id}")
async def get_buyer(buyer_id: str):
    return {"buyer_id": buyer_id, "business_name": "Buyer profile will appear here after provider integration."}
