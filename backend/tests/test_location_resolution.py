import unittest
from unittest.mock import patch

from app.services.location import NominatimLocationResolver


class LocationResolutionCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_location_is_reused_by_new_resolver_instances(self):
        location = "BuyerBridge cache regression city, NY"
        cache_key = (
            "https://nominatim.example/search|"
            f"{location.casefold()}|united states"
        )
        NominatimLocationResolver._cache.pop(cache_key, None)
        requests = []

        class Response:
            status_code = 200

            @staticmethod
            def json():
                return [{
                    "lat": "40.7128",
                    "lon": "-74.0060",
                    "display_name": "New York, United States",
                    "boundingbox": ["40.4", "40.9", "-74.3", "-73.7"],
                    "address": {
                        "city": "New York",
                        "state": "New York",
                        "country": "United States",
                        "country_code": "us",
                    },
                }]

        class AsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def get(self, url, params):
                requests.append((url, params))
                return Response()

        with patch("app.services.location.httpx.AsyncClient", AsyncClient):
            first = await NominatimLocationResolver(
                api_url="https://nominatim.example/search"
            ).resolve(location, "United States")
            second = await NominatimLocationResolver(
                api_url="https://nominatim.example/search"
            ).resolve(location.upper(), "UNITED STATES")

        self.assertEqual(len(requests), 1)
        self.assertEqual(first["city"], "New York")
        self.assertEqual(second["boundingbox"], first["boundingbox"])
        self.assertIsNot(second["boundingbox"], first["boundingbox"])
