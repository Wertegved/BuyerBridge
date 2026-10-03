import unittest
from unittest.mock import AsyncMock
from unittest.mock import patch

from app.routes.search import enrich_buyer_result
from app.services.business_search import extract_osm_website
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

    async def test_missing_website_skips_enrichment(self):
        enrichment_service = AsyncMock()
        result = {
            "website": None,
            "email": "old@example.com",
            "email_available": True,
            "contact_source": "osm",
        }

        enriched_result = await enrich_buyer_result(result, enrichment_service)

        enrichment_service.enrich.assert_not_awaited()
        self.assertEqual(
            enriched_result,
            {
                "website": None,
                "email": None,
                "email_available": False,
                "contact_source": None,
            },
        )

    async def test_unusable_website_skips_enrichment(self):
        enrichment_service = AsyncMock()
        result = {"website": "Website unavailable", "email": None, "email_available": False}

        enriched_result = await enrich_buyer_result(result, enrichment_service)

        enrichment_service.enrich.assert_not_awaited()
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


if __name__ == "__main__":
    unittest.main()
