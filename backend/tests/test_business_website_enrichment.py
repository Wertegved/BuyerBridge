import unittest
from unittest.mock import AsyncMock
from unittest.mock import patch

from app.routes.search import enrich_buyer_result
from app.services.business_search import (
    OverpassBusinessSearchProvider,
    build_overpass_query,
    deduplicate_businesses,
    extract_osm_tag,
    extract_osm_website,
    get_supported_tags,
    hydrate_osm_metadata,
    score_business,
)
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
            (
                {"extratags": {"contact:website": "https://extratags.example.com"}},
                "https://extratags.example.com",
            ),
            (
                {"tags": [{"key": "url", "value": "https://nested-tags.example.com"}]},
                "https://nested-tags.example.com",
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

    def test_extracts_email_from_nominatim_extratags(self):
        self.assertEqual(
            extract_osm_tag(
                {"extratags": {"contact:email": " hello@example.com "}},
                ("email", "contact:email"),
            ),
            "hello@example.com",
        )

    def test_duplicate_businesses_keep_website_and_email_from_all_records(self):
        results = deduplicate_businesses([
            {
                "provider_id": "osm:node:1",
                "business_name": "Same Studio",
                "address": "1 Main Street",
                "website": None,
                "email": None,
            },
            {
                "provider_id": "osm:way:2",
                "business_name": "Same Studio",
                "address": "1 Main Street",
                "website": "https://same.example",
                "email": "hello@same.example",
                "email_available": True,
                "contact_source": "openstreetmap",
            },
        ])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["website"], "https://same.example")
        self.assertEqual(results[0]["email"], "hello@same.example")
        self.assertTrue(results[0]["email_available"])


class BuyerWebsiteEnrichmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_overpass_zero_results_runs_photon_and_returns_business(self):
        photon_requests = []

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

            async def post(self, url, data):
                return Response({"elements": []})

            async def get(self, url, params):
                if "nominatim" in url:
                    return Response([])
                photon_requests.append((url, params))
                features = [{
                    "geometry": {"coordinates": [-74.0, 40.7]},
                    "properties": {
                        "name": "Real Interior Design Studio",
                        "osm_type": "N",
                        "osm_id": 42,
                        "osm_key": "craft",
                        "osm_value": "interior_design",
                        "city": "New York",
                    },
                }] if params["osm_tag"] == "craft:interior_design" else []
                return Response({
                    "features": features,
                })

        provider = OverpassBusinessSearchProvider(api_url="https://overpass.example")
        location = {
            "latitude": 40.7,
            "longitude": -74.0,
            "boundingbox": ["40.5", "40.9", "-74.2", "-73.7"],
            "city": "New York",
            "state": "NY",
        }
        with patch("app.services.business_search.httpx.AsyncClient", AsyncClient):
            results = await provider.search("Interior Designers", location, 10)

        self.assertTrue(photon_requests)
        self.assertEqual(photon_requests[0][0], "https://photon.komoot.io/api/")
        self.assertEqual(photon_requests[0][1]["q"], "interior")
        self.assertEqual(photon_requests[0][1]["bbox"], "-74.2,40.5,-73.7,40.9")
        self.assertEqual(results[0]["business_name"], "Real Interior Design Studio")
        self.assertEqual(results[0]["provider_id"], "osm:N:42")

    async def test_first_empty_overpass_endpoint_continues_to_second(self):
        posted_urls = []

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

            async def post(self, url, data):
                posted_urls.append(url)
                if url.endswith("second"):
                    return Response({
                        "elements": [{
                            "type": "node",
                            "id": 7,
                            "tags": {"name": "Second Endpoint Studio", "shop": "furniture"},
                        }],
                    })
                return Response({"elements": []})

            async def get(self, url, params):
                return Response([])

        provider = OverpassBusinessSearchProvider()
        provider.api_urls = ("https://overpass.example/first", "https://overpass.example/second")
        with patch("app.services.business_search.httpx.AsyncClient", AsyncClient):
            results = await provider.search(
                "Furniture Stores",
                {"latitude": 40.7, "longitude": -74.0, "city": "New York"},
                10,
            )

        self.assertEqual(posted_urls, list(provider.api_urls))
        self.assertEqual(results[0]["business_name"], "Second Endpoint Studio")

    async def test_all_empty_overpass_endpoints_fall_back_to_photon(self):
        posted_urls = []
        photon_calls = []

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

            async def post(self, url, data):
                posted_urls.append(url)
                return Response({"elements": []})

            async def get(self, url, params):
                if "nominatim" in url:
                    return Response([])
                photon_calls.append(url)
                return Response({"features": []})

        provider = OverpassBusinessSearchProvider()
        provider.api_urls = ("https://overpass.example/1", "https://overpass.example/2", "https://overpass.example/3")
        with patch("app.services.business_search.httpx.AsyncClient", AsyncClient):
            results = await provider.search(
                "Furniture Stores",
                {"latitude": 40.7, "longitude": -74.0, "city": "New York"},
                10,
            )

        self.assertEqual(len(posted_urls), 3)
        self.assertTrue(photon_calls)
        self.assertEqual(results, [])

    async def test_photon_rejects_features_outside_resolved_bbox(self):
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

            async def post(self, url, data):
                return Response({"elements": []})

            async def get(self, url, params):
                if "nominatim" in url:
                    return Response([])
                return Response({
                    "features": [
                        {
                            "geometry": {"coordinates": [-74.0, 40.7]},
                            "properties": {
                                "name": "Inside Bounds",
                                "osm_type": "N",
                                "osm_id": 101,
                                "osm_key": "shop",
                                "osm_value": "furniture",
                            },
                        },
                        {
                            "geometry": {"coordinates": [-73.0, 40.7]},
                            "properties": {
                                "name": "Outside Bounds",
                                "osm_type": "N",
                                "osm_id": 102,
                                "osm_key": "shop",
                                "osm_value": "furniture",
                            },
                        },
                    ],
                })

        provider = OverpassBusinessSearchProvider(api_url="https://overpass.example")
        with patch("app.services.business_search.httpx.AsyncClient", AsyncClient):
            results = await provider.search(
                "Furniture Stores",
                {
                    "latitude": 40.7,
                    "longitude": -74.0,
                    "boundingbox": ["40.5", "40.9", "-74.2", "-73.7"],
                    "city": "New York",
                },
                10,
            )

        self.assertEqual([result["business_name"] for result in results], ["Inside Bounds"])

    async def test_overpass_metadata_hydration_recovers_website_and_email(self):
        lookup_calls = []

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

            async def post(self, url, data):
                return Response({
                    "elements": [{
                        "type": "node",
                        "id": 12,
                        "tags": {"name": "Hydrated Studio", "shop": "furniture"},
                    }],
                })

            async def get(self, url, params):
                lookup_calls.append((url, params))
                return Response([{
                    "osm_type": "node",
                    "osm_id": 12,
                    "extratags": {
                        "contact:website": "https://hydrated.example",
                        "contact:email": "hello@hydrated.example",
                    },
                }])

        provider = OverpassBusinessSearchProvider(api_url="https://overpass.example")
        with patch("app.services.business_search.httpx.AsyncClient", AsyncClient):
            results = await provider.search(
                "Furniture Stores",
                {"latitude": 40.7, "longitude": -74.0, "city": "New York"},
                10,
            )

        self.assertEqual(lookup_calls[0][0], "https://nominatim.openstreetmap.org/lookup")
        self.assertEqual(lookup_calls[0][1]["osm_ids"], "N12")
        self.assertEqual(results[0]["website"], "https://hydrated.example")
        self.assertEqual(results[0]["email"], "hello@hydrated.example")
        self.assertTrue(results[0]["email_available"])
        self.assertEqual(results[0]["contact_source"], "openstreetmap")
        self.assertEqual(results[0]["provider_id"], "osm:node:12")

    async def test_hydration_never_clears_existing_website_or_email(self):
        business = {
            "provider_id": "osm:node:4",
            "website": "https://existing.example",
            "email": "existing@example.com",
            "email_available": True,
            "_osm_ref": ("node", 4),
        }
        with patch(
            "app.services.business_search.lookup_osm_metadata_by_ids",
            AsyncMock(return_value={"N4": {"extratags": {}, "address": {}}}),
        ):
            hydrated = await hydrate_osm_metadata([business])

        self.assertIs(hydrated[0], business)
        self.assertEqual(business["website"], "https://existing.example")
        self.assertEqual(business["email"], "existing@example.com")
        self.assertTrue(business["email_available"])
        self.assertEqual(business["contact_source"], "openstreetmap")
        self.assertNotIn("_osm_ref", business)

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

    async def test_company_search_domain_and_findymail_email_update_original_result(self):
        enrichment_service = AsyncMock()
        enrichment_service.enrich.return_value = {
            "website": "https://found-domain.example",
            "email": "person@found-domain.example",
            "email_available": True,
            "contact_source": "findymail",
        }
        result = {
            "business_name": "Domain Lookup Studio",
            "website": None,
            "email": "osm@original.example",
            "email_available": True,
            "contact_source": "openstreetmap",
        }

        enriched_result = await enrich_buyer_result(result, enrichment_service)

        self.assertIs(enriched_result, result)
        self.assertEqual(result["website"], "https://found-domain.example")
        self.assertEqual(result["email"], "person@found-domain.example")
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
        request_headers = []
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
                request_headers.append(headers)
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
        self.assertEqual(request_headers[0]["Authorization"], "Bearer test-api-key")
        self.assertEqual(request_headers[1]["Authorization"], "Bearer test-api-key")
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

    async def test_photon_osm_lookup_recovers_website_email_and_keeps_existing_values(self):
        class PhotonResponse:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "features": [
                        {
                            "properties": {
                                "name": "Recovered Studio",
                                "osm_type": "N",
                                "osm_id": 99,
                                "osm_key": "shop",
                                "osm_value": "furniture",
                                "city": "New York",
                                "state": "NY",
                                "country": "United States",
                                "osm_tags": {
                                    "website": "https://recovered.example",
                                    "contact:email": "recovered@example.com",
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

            async def post(self, url, data=None, **kwargs):
                return type("Response", (), {"status_code": 504, "json": lambda self: {}})()

            async def get(self, url, params=None):
                return PhotonResponse()

        provider = OverpassBusinessSearchProvider(api_url="https://overpass.example")
        location = {"latitude": 40.7, "longitude": -74.0, "city": "New York", "state": "NY", "country": "United States"}
        with patch("app.services.business_search.httpx.AsyncClient", AsyncClient):
            with patch("app.services.business_search.OVERPASS_ENDPOINTS", ("https://overpass.example",)):
                with patch("app.services.business_search.lookup_osm_metadata_by_ids", AsyncMock(return_value={"N99": {"extratags": {"website": "https://recovered.example", "contact:email": "recovered@example.com"}, "address": {"city": "New York", "state": "New York", "country": "United States"}}})) as lookup_mock:
                    results = await provider.search("Furniture Stores", location, 10)

        lookup_mock.assert_awaited_once_with([("N", 99)])
        self.assertEqual(results[0]["website"], "https://recovered.example")
        self.assertEqual(results[0]["email"], "recovered@example.com")
        self.assertNotIn("_osm_ref", results[0])

    def test_relevance_scoring_distinguishes_city_and_category_matches(self):
        nearby = {
            "business_name": "Home Goods Supply",
            "category": "Home Decor",
            "city": "Brooklyn",
            "state": "NY",
            "website": "https://goods.example",
            "email": "goods@example.com",
            "requested_city": "New York",
        }
        exact = {
            "business_name": "City Design Studio",
            "category": "Interior Design",
            "city": "New York",
            "state": "NY",
            "website": "https://design.example",
            "email": "design@example.com",
            "requested_city": "New York",
        }
        self.assertGreater(
            score_business(exact, "Interior Designers", ["furniture", "living", "room"]),
            score_business(nearby, "Interior Designers", ["furniture", "living", "room"]),
        )

    def test_overpass_bbox_query_uses_requested_limit_up_to_50(self):
        query = build_overpass_query("furniture stores", {
            "latitude": 40.5,
            "longitude": -73.5,
            "boundingbox": ["40.0", "41.0", "-74.1", "-73.0"],
        }, 50)
        self.assertIn("out center tags 50;", query)
        self.assertIn("(40.0,-74.1,41.0,-73.0)", query)
        self.assertIn("nwr[shop=furniture]", query)
        self.assertNotIn("nwr[shop:furniture]", query)

    def test_all_buyer_type_tags_are_retained(self):
        tags = get_supported_tags("Interior Designers")
        self.assertGreaterEqual(
            set(tags),
            {
                "craft:interior_design",
                "office:interior_design",
                "shop:furniture",
                "shop:interior_decoration",
                "shop:decor",
                "shop:gift",
                "shop:home_furniture",
            },
        )

    def test_exact_category_and_city_score_higher_than_generic_and_outside(self):
        exact = {
            "business_name": "Interior Design Firm",
            "category": "Interior Design",
            "city": "New York",
            "state": "NY",
            "requested_city": "New York",
            "requested_state": "NY",
        }
        generic = {
            **exact,
            "business_name": "Local Business",
            "category": "Business",
            "city": "Buffalo",
        }
        exact_score = score_business(exact, "Interior Designers", [])
        generic_score = score_business(generic, "Interior Designers", [])
        self.assertGreater(exact_score, generic_score)

        outside_city = {**exact, "city": "Brooklyn"}
        self.assertGreater(
            score_business(exact, "Interior Designers", []),
            score_business(outside_city, "Interior Designers", []),
        )

    def test_website_and_email_are_five_point_bonuses(self):
        base = {
            "business_name": "Studio",
            "category": "Business",
            "city": "New York",
            "requested_city": "New York",
        }
        base_score = score_business(base, "Interior Designers", [])
        website_score = score_business({**base, "website": "https://studio.example"}, "Interior Designers", [])
        email_score = score_business({**base, "email": "hello@studio.example"}, "Interior Designers", [])
        self.assertEqual(website_score - base_score, 5)
        self.assertEqual(email_score - base_score, 5)


if __name__ == "__main__":
    unittest.main()
