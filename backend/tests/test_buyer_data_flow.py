from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database.tables import Base
from app.models.buyer import Buyer
from app.models.search import Search
from app.routes.buyers import list_buyers
from app.routes.search import search_buyers
from app.schemas.search import SearchRequest


class BuyerPersistenceFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_final_enriched_buyer_values_are_persisted_and_returned(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as database:
                discovered = {
                    "provider_id": "osm:node:1",
                    "business_name": "Example Studio",
                    "category": "Interior Design",
                    "address": "1 Main Street",
                    "city": "New York",
                    "state": "NY",
                    "country": "United States",
                    "website": "https://example.com",
                    "phone": "+1 212 555 0100",
                    "email": "osm@example.com",
                    "email_available": True,
                    "source": "openstreetmap",
                    "contact_source": None,
                    "relevance_score": 85,
                }

                async def enrich(buyer):
                    buyer["email"] = "person@example.com"
                    buyer["email_available"] = True
                    buyer["contact_source"] = "findymail"
                    return buyer

                enrichment = AsyncMock()
                enrichment.enrich.side_effect = enrich
                location_resolver = SimpleNamespace(
                    resolve=AsyncMock(
                        return_value={
                            "latitude": 40.7,
                            "longitude": -74.0,
                            "city": "New York",
                        }
                    )
                )

                with (
                    patch(
                        "app.routes.search.NominatimLocationResolver",
                        return_value=location_resolver,
                    ),
                    patch(
                        "app.routes.search.BusinessSearchService",
                        return_value=SimpleNamespace(
                            search=AsyncMock(return_value=[discovered])
                        ),
                    ),
                    patch("app.routes.search.OverpassBusinessSearchProvider"),
                    patch(
                        "app.routes.search.ContactEnrichmentService",
                        return_value=enrichment,
                    ),
                    patch("app.routes.search.FindymailContactEnrichment"),
                ):
                    response = await search_buyers(
                        SearchRequest(
                            product_category="Furniture",
                            product_description="Commercial furniture for design projects",
                            buyer_type="Interior Designers",
                            location="New York, NY",
                            country="United States",
                            limit=10,
                        ),
                        current_user=SimpleNamespace(id=7),
                        database=database,
                    )

                persisted = database.execute(select(Buyer)).scalar_one()
                result = response["results"][0]
                self.assertEqual(result["id"], str(persisted.id))
                self.assertEqual(result["business_name"], "Example Studio")
                self.assertEqual(result["website"], "https://example.com")
                self.assertEqual(result["email"], "person@example.com")
                self.assertTrue(result["email_available"])
                self.assertEqual(result["contact_source"], "findymail")
                self.assertEqual(result["phone"], "+1 212 555 0100")
                self.assertEqual(result["category"], persisted.category)
                self.assertEqual(result["address"], persisted.address)
                self.assertEqual(result["city"], persisted.city)
                self.assertEqual(result["state"], persisted.state)
                self.assertEqual(result["country"], persisted.country)
                self.assertEqual(result["source"], persisted.source)
                self.assertEqual(result["relevance_score"], persisted.relevance_score)
                self.assertEqual(persisted.website, "https://example.com")
                self.assertEqual(persisted.email, "person@example.com")
        finally:
            Base.metadata.drop_all(engine)
            engine.dispose()


class BuyerIdFilterTests(unittest.IsolatedAsyncioTestCase):
    async def test_buyers_endpoint_returns_requested_records_with_latest_contact_fields(self):
        latest = SimpleNamespace(
            id=42,
            business_name="Latest Studio",
            category="Interior Design",
            address="2 Main Street",
            city="New York",
            state="NY",
            country="United States",
            website="https://latest.example",
            phone=None,
            email="latest@example.com",
            email_available=True,
            source="openstreetmap",
            contact_source="findymail",
            relevance_score=90,
        )
        older = SimpleNamespace(
            id=41,
            business_name="Older Studio",
            category="Interior Design",
            address="3 Main Street",
            city="New York",
            state="NY",
            country="United States",
            website="https://older.example",
            phone=None,
            email="older@example.com",
            email_available=True,
            source="openstreetmap",
            contact_source="openstreetmap",
            relevance_score=70,
        )

        with patch(
            "app.routes.buyers.get_buyers_for_user",
            return_value=[older, latest],
        ):
            response = await list_buyers(
                ids=["42"],
                current_user=SimpleNamespace(id=7),
                database=object(),
            )

        self.assertEqual(len(response["buyers"]), 1)
        self.assertEqual(response["buyers"][0]["id"], "42")
        self.assertEqual(response["buyers"][0]["business_name"], "Latest Studio")
        self.assertEqual(response["buyers"][0]["website"], "https://latest.example")
        self.assertEqual(response["buyers"][0]["email"], "latest@example.com")
