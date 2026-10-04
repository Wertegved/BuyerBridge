from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.buyer import Buyer
from app.models.search import Search as SearchRecord
from app.models.user import User
from app.routes.auth import get_current_user
from app.schemas.search import SearchRequest
from app.services.business_search import (
    BusinessSearchService,
    OverpassBusinessSearchProvider,
    extract_osm_website,
)
from app.services.contact_enrichment import ContactEnrichmentService, FindymailContactEnrichment
from app.services.location import LocationResolutionError, NominatimLocationResolver

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


async def enrich_buyer_result(result: dict, enrichment_service: ContactEnrichmentService) -> dict:
    website = extract_osm_website(result) or result.get("website")
    if website and not result.get("website"):
        result["website"] = website
    domain = FindymailContactEnrichment._extract_domain(website)
    business_name = result.get("business_name") or "Business name unavailable"
    enrichment_input = {**result, "website": domain}
    if website and not domain:
        enrichment_input["website"] = None

    logger.info(
        "Findymail enrichment for %s: usable_domain=%s, domain=%s",
        business_name,
        str(bool(domain)).lower(),
        domain or "company lookup required",
    )
    try:
        enriched = await enrichment_service.enrich(enrichment_input)
    except Exception:
        logger.exception("Findymail enrichment failed for %s", business_name)
        logger.info("Findymail enrichment for %s: email_returned=false", business_name)
        return result

    returned_website = enriched.get("website") if isinstance(enriched, dict) else None
    returned_domain = FindymailContactEnrichment._extract_domain(returned_website)
    if returned_domain and not domain:
        result["website"] = f"https://{returned_domain}"
        logger.info(
            "Findymail enrichment for %s: company_domain_found=%s",
            business_name,
            returned_domain,
        )

    email = enriched.get("email") if isinstance(enriched, dict) else None
    email_returned = (
        isinstance(email, str)
        and bool(email.strip())
        and "@" in email
        and enriched.get("contact_source") == "findymail"
    )
    logger.info(
        "Findymail enrichment for %s: email_returned=%s",
        business_name,
        str(email_returned).lower(),
    )
    if email_returned:
        for field in ("email", "email_available", "contact_source"):
            result[field] = enriched[field]
    return result


def serialize_persisted_buyer(buyer: Buyer, provider_id: str | None = None) -> dict:
    return {
        "id": str(buyer.id),
        "provider_id": provider_id,
        "business_name": buyer.business_name,
        "website": buyer.website,
        "email": buyer.email,
        "email_available": buyer.email_available,
        "contact_source": buyer.contact_source,
        "phone": buyer.phone,
        "category": buyer.category,
        "address": buyer.address,
        "city": buyer.city,
        "state": buyer.state,
        "country": buyer.country,
        "source": buyer.source,
        "relevance_score": buyer.relevance_score,
    }


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
    final_results = []
    for index, result in enumerate(results):
        results[index] = await enrich_buyer_result(result, contact_enrichment)
        result = results[index]
        logger.info(
            "Buyer ready for persistence: business_name=%s website=%s email=%s contact_source=%s",
            result.get("business_name"),
            result.get("website"),
            result.get("email"),
            result.get("contact_source"),
        )

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
            email_available=bool(result.get("email_available") or result.get("email")),
            source=result.get("source"),
            contact_source=result.get("contact_source"),
            relevance_score=result.get("relevance_score") or 0,
        )
        database.add(buyer)
        database.flush()
        result.update(
            serialize_persisted_buyer(
                buyer,
                provider_id=result.get("provider_id"),
            )
        )
        logger.info(
            "Buyer persisted: business_name=%s website=%s email=%s contact_source=%s",
            result["business_name"],
            result["website"],
            result["email"],
            result["contact_source"],
        )
        final_results.append(result)

    database.commit()

    return {
        "status": "ok",
        "message": "Potential buyers found.",
        "results": final_results,
    }
