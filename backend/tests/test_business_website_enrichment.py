import unittest
from unittest.mock import AsyncMock
from unittest.mock import patch

from app.routes.search import enrich_buyer_result
from app.services.business_search import OverpassBusinessSearchProvider, extract_osm_website
from app.services.contact_enrichment import ContactEnrichmentService, FindymailContactEnrichment


class BusinessWebsiteExtractionTests(unittest.TestCase):
    def test_extracts_available_osm_website_fields(self):
        cases = (
            ({"website": "https://www.example.com/about"}, "https://www.example.com/about"),
            ({"contact:website": "https://contact.example.com"}, "https://contact.example.com"),
            ({"url": "https://url.example.com"}, "https://url.example.com"),
            ({"contact:url": "https://contact-url.example.com"}, "https://contact-url.example.com"),
            (
                {"osm_tags": {"website": "https://nested.example.com"}},
                "https://nested.example.com",
            ),
            (
                {"osm_tags": [{"key": "contact:website", "value": "nested-list.example.com"}]},
                "nested-list.example.com",
            ),
        )
        for properties, expected in cases:
            with self.subTest(properties=properties):
                self.assertEqual(extract_osm_website(properties), expected)

    def test_prefers_direct_website_over_nested_tags(self):
        self.assertEqual(
            extract_osm_website(
                {
                    "website": "direct.example.com",
                    "osm_tags": {"website": "nested.example.com"},
                }
            ),
            "direct.example.com",
        )


class BuyerWebsiteEnrichmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_overpass_mapping_preserves_osm_website_and_email(self):
        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "elements": [
                        {
                            "type": "node",
                            "id": 12,
                            "tags": {
                                "name": "OSM Studio",
                                "shop": "furniture",
                                "addr:street": "1 Main Street",
                                "website": "https://osm.example",
                                "email": "osm@example.com",
                                "phone": "+1 212 555 0100",
                            },
                        }
                    ]
                }

        class AsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, url, data):
                return Response()

        provider = OverpassBusinessSearchProvider(api_url="https://overpass.example")
        location = {"latitude": 40.7, "longitude": -74.0, "city": "New York"}
        with patch("app.services.business_search.httpx.AsyncClient", AsyncClient):
            results = await provider.search("Furniture Stores", location, 10)

        self.assertEqual(results[0]["website"], "https://osm.example")
        self.assertEqual(results[0]["email"], "osm@example.com")
        self.assertTrue(results[0]["email_available"])
        self.assertEqual(results[0]["phone"], "+1 212 555 0100")

    async def test_photon_mapping_preserves_nested_osm_website_email_and_phone(self):
        class OverpassResponse:
            status_code = 504

            @staticmethod
            def json():
                return {}

        class PhotonResponse:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "features": [
                        {
                            "properties": {
                                "name": "Photon Studio",
                                "osm_type": "N",
                                "osm_id": 15,
                                "osm_key": "shop",
                                "osm_value": "furniture",
                                "city": "New York",
                                "osm_tags": {
                                    "contact:website": "https://photon.example",
                                    "contact:email": "photon@example.com",
                                    "contact:phone": "+1 212 555 0102",
                                },
                            }
                        }
                    ]
                }

        class AsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, url, data):
                return OverpassResponse()

            async def get(self, url, params):
                return PhotonResponse()

        provider = OverpassBusinessSearchProvider(api_url="https://overpass.example")
        location = {"latitude": 40.7, "longitude": -74.0, "city": "New York"}
        with patch("app.services.business_search.httpx.AsyncClient", AsyncClient):
            results = await provider.search("Furniture Stores", location, 10)

        self.assertEqual(results[0]["website"], "https://photon.example")
        self.assertEqual(results[0]["email"], "photon@example.com")
        self.assertTrue(results[0]["email_available"])
        self.assertEqual(results[0]["phone"], "+1 212 555 0102")

    async def test_passes_normalized_domain_to_enrichment(self):
        enrichment_service = AsyncMock()
        enrichment_service.enrich.return_value = {
            "website": "example.com",
            "email": "person@example.com",
            "email_available": True,
            "contact_source": "findymail",
        }
        result = {"website": "https://www.example.com/contact"}

        enriched_result = await enrich_buyer_result(result, enrichment_service)

        enrichment_service.enrich.assert_awaited_once_with({"website": "example.com"})
        self.assertIs(enriched_result, result)
        self.assertEqual(result["email"], "person@example.com")
        self.assertTrue(result["email_available"])
        self.assertEqual(result["contact_source"], "findymail")

    async def test_missing_website_preserves_osm_email_and_phone(self):
        enrichment_service = AsyncMock()
        result = {
            "business_name": "OSM Studio",
            "website": None,
            "email": "old@example.com",
            "email_available": True,
            "contact_source": "openstreetmap",
            "phone": "+1 212 555 0100",
        }

        enriched_result = await enrich_buyer_result(result, enrichment_service)

        enrichment_service.enrich.assert_awaited_once_with(result.copy())
        self.assertEqual(
            enriched_result,
            result,
        )

    async def test_unusable_website_preserves_original_fields(self):
        enrichment_service = AsyncMock()
        result = {
            "business_name": "OSM Studio",
            "website": "Website unavailable",
            "email": "osm@example.com",
            "email_available": True,
            "phone": "+1 212 555 0100",
            "contact_source": "openstreetmap",
        }

        enriched_result = await enrich_buyer_result(result, enrichment_service)

        enrichment_service.enrich.assert_awaited_once()
        self.assertEqual(enriched_result, result)

    async def test_findymail_contacts_response_updates_original_buyer(self):
        requests = []

        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {"contacts": [{"email": "person@example.com"}]}

        class AsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, url, headers, json):
                requests.append(json)
                return Response()

        buyer = {
            "business_name": "Example Studio",
            "website": "https://www.example.com/contact",
            "email": None,
            "email_available": False,
            "contact_source": None,
        }
        enrichment_service = ContactEnrichmentService(
            FindymailContactEnrichment(api_key="test-api-key")
        )

        with patch("app.services.contact_enrichment.httpx.AsyncClient", AsyncClient):
            result = await enrich_buyer_result(buyer, enrichment_service)

        self.assertIs(result, buyer)
        self.assertEqual(buyer["email"], "person@example.com")
        self.assertIs(buyer["email_available"], True)
        self.assertEqual(buyer["contact_source"], "findymail")
        self.assertEqual(buyer["website"], "https://www.example.com/contact")
        self.assertEqual(requests[0]["domain"], "example.com")

    async def test_failed_findymail_preserves_existing_website_email_and_phone(self):
        enrichment_service = AsyncMock()
        enrichment_service.enrich.side_effect = RuntimeError("temporary failure")
        buyer = {
            "business_name": "Example Studio",
            "website": "https://example.com",
            "email": "existing@example.com",
            "email_available": True,
            "phone": "+1 212 555 0100",
            "contact_source": "openstreetmap",
        }

        result = await enrich_buyer_result(buyer, enrichment_service)

        self.assertEqual(result, buyer)

    async def test_no_website_company_searches_domain_then_contact_email(self):
        requests = []
        responses = [
            {"domain": "example.com"},
            {"contacts": [{"email": "PERSON@EXAMPLE.COM"}]},
        ]

        class Response:
            status_code = 200

            def __init__(self, body):
                self.body = body

            def json(self):
                return self.body

        class AsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, url, headers, json):
                requests.append((url, json))
                return Response(responses.pop(0))

        buyer = {
            "business_name": "Example Studio",
            "website": None,
            "email": "osm@example.com",
            "email_available": True,
            "phone": "+1 212 555 0100",
            "contact_source": "openstreetmap",
        }
        service = ContactEnrichmentService(
            FindymailContactEnrichment(api_key="test-api-key")
        )

        with patch("app.services.contact_enrichment.httpx.AsyncClient", AsyncClient):
            result = await service.enrich(buyer)

        self.assertEqual(requests[0][0], FindymailContactEnrichment.COMPANY_API_URL)
        self.assertEqual(requests[0][1], {"name": "Example Studio"})
        self.assertEqual(requests[1][0], FindymailContactEnrichment.API_URL)
        self.assertEqual(requests[1][1]["domain"], "example.com")
        self.assertEqual(result["website"], "https://example.com")
        self.assertEqual(result["email"], "person@example.com")
        self.assertTrue(result["email_available"])
        self.assertEqual(result["contact_source"], "findymail")
        self.assertEqual(result["phone"], "+1 212 555 0100")

    async def test_singular_findymail_contact_response_is_parsed(self):
        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {"contact": {"email": "SINGLE@EXAMPLE.COM"}}

        class AsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, url, headers, json):
                return Response()

        service = FindymailContactEnrichment(api_key="test-api-key")
        buyer = {"business_name": "Example", "website": "example.com"}

        with patch("app.services.contact_enrichment.httpx.AsyncClient", AsyncClient):
            await service.enrich(buyer)

        self.assertEqual(buyer["email"], "single@example.com")
        self.assertTrue(buyer["email_available"])
        self.assertEqual(buyer["contact_source"], "findymail")


if __name__ == "__main__":
    unittest.main()
