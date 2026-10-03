from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.models.buyer import Buyer
from app.routes.buyers import list_buyers
from app.routes.search import search_buyers
from app.schemas.search import SearchRequest


class FakeDatabase:
    def __init__(self):
        self.objects = []
        self.next_buyer_id = 500

    def add(self, item):
        self.objects.append(item)

    def flush(self):
        item = self.objects[-1]
        if isinstance(item, Buyer):
            self.next_buyer_id += 1
            item.id = self.next_buyer_id

    def commit(self):
        pass


class BuyerPersistenceFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_response_contains_persisted_buyer_id_and_final_contact_fields(self):
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
            "email": None,
            "email_available": False,
            "source": "openstreetmap",
            "contact_source": None,
            "relevance_score": 85,
        }
        enrichment = AsyncMock()
        enrichment.enrich.side_effect = _enriched
        database = FakeDatabase()
        location_resolver = SimpleNamespace(
            resolve=AsyncMock(
                return_value={"latitude": 40.7, "longitude": -74.0, "city": "New York"}
            )
        )

        with (
            patch("app.routes.search.NominatimLocationResolver", return_value=location_resolver),
            patch(
                "app.routes.search.BusinessSearchService",
                return_value=SimpleNamespace(search=AsyncMock(return_value=[discovered])),
            ),
            patch("app.routes.search.OverpassBusinessSearchProvider"),
            patch("app.routes.search.ContactEnrichmentService", return_value=enrichment),
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

        buyer = next(item for item in database.objects if isinstance(item, Buyer))
        self.assertEqual(response["results"][0]["id"], str(buyer.id))
        self.assertEqual(response["results"][0]["website"], buyer.website)
        self.assertEqual(response["results"][0]["phone"], buyer.phone)
        self.assertEqual(response["results"][0]["email"], buyer.email)
        self.assertEqual(response["results"][0]["email"], "person@example.com")
        self.assertTrue(response["results"][0]["email_available"])
        self.assertEqual(response["results"][0]["contact_source"], "findymail")


async def _enriched(buyer):
    buyer["email"] = "person@example.com"
    buyer["email_available"] = True
    buyer["contact_source"] = "findymail"
    return buyer


class BuyerIdFilterTests(unittest.IsolatedAsyncioTestCase):
    async def test_buyers_endpoint_returns_only_requested_latest_buyer_records(self):
        latest = SimpleNamespace(
            id=42,
            business_name="Latest Studio",
            category="Interior Design",
            address="2 Main Street",
            city="New York",
            state="NY",
            country="United States",
            website="https://latest.example",
            phone="+1 212 555 0101",
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
