import unittest
from unittest.mock import AsyncMock

from app.routes.search import enrich_buyer_result
from app.services.business_search import extract_osm_website


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
        result = {"website": "https://www.example.com/contact"}

        enriched_result = await enrich_buyer_result(result, enrichment_service)

        enrichment_service.enrich.assert_awaited_once_with({"website": "example.com"})
        self.assertIs(enriched_result, result)

    async def test_missing_website_skips_enrichment(self):
        enrichment_service = AsyncMock()
        result = {"website": None, "email": None, "email_available": False}

        enriched_result = await enrich_buyer_result(result, enrichment_service)

        enrichment_service.enrich.assert_not_awaited()
        self.assertEqual(enriched_result, result)

    async def test_unusable_website_skips_enrichment(self):
        enrichment_service = AsyncMock()
        result = {"website": "Website unavailable", "email": None, "email_available": False}

        enriched_result = await enrich_buyer_result(result, enrichment_service)

        enrichment_service.enrich.assert_not_awaited()
        self.assertEqual(enriched_result, result)


if __name__ == "__main__":
    unittest.main()
