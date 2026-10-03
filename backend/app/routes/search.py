from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.buyer import Buyer
from app.models.search import Search as SearchRecord
from app.models.user import User
from app.routes.auth import get_current_user
from app.schemas.search import SearchRequest
from app.services.business_search import BusinessSearchService, OverpassBusinessSearchProvider
from app.services.contact_enrichment import ContactEnrichmentService, FindymailContactEnrichment
from app.services.location import LocationResolutionError, NominatimLocationResolver

router = APIRouter(prefix="/api")


@router.post("/search-buyers")
async def search_buyers(
    payload: SearchRequest,
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
):
    if payload.country.strip().lower() not in {"united states", "us", "usa"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="BuyerBridge currently supports United States locations only.",
        )

    try:
        resolved_location = await NominatimLocationResolver().resolve(payload.location, payload.country)
    except LocationResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        results = await BusinessSearchService(OverpassBusinessSearchProvider()).search(
            query=payload.buyer_type,
            location={
                **resolved_location,
                "product_category": payload.product_category,
                "product_description": payload.product_description,
            },
            limit=payload.limit,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    contact_enrichment = ContactEnrichmentService(FindymailContactEnrichment())
    for index, result in enumerate(results):
        results[index] = await contact_enrichment.enrich(result)

    search_record = SearchRecord(
        user_id=current_user.id,
        product_category=payload.product_category,
        product_description=payload.product_description,
        buyer_type=payload.buyer_type,
        location=payload.location,
        country=payload.country,
        result_count=len(results),
    )
    database.add(search_record)
    database.flush()

    for result in results:
        buyer = Buyer(
            business_name=result.get("business_name") or "Business name unavailable",
            category=result.get("category"),
            address=result.get("address"),
            city=result.get("city"),
            state=result.get("state"),
            country=result.get("country"),
            website=result.get("website"),
            phone=result.get("phone"),
            email=result.get("email"),
            email_available=bool(result.get("email")),
            source=result.get("source"),
            contact_source=result.get("contact_source"),
            relevance_score=result.get("relevance_score") or 0,
        )
        database.add(buyer)
        database.flush()

    database.commit()

    return {
        "status": "ok",
        "message": "Potential buyers found.",
        "results": results,
    }
