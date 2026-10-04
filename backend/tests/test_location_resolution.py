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

    async def test_photon_resolves_location_when_nominatim_is_rate_limited(self):
        location = "BuyerBridge fallback test, NY"
        api_url = "https://nominatim.example/search"
        cache_key = f"{api_url}|{location.casefold()}|united states"
        NominatimLocationResolver._cache.pop(cache_key, None)
        requests = []

        class Response:
            def __init__(self, status_code, body):
                self.status_code = status_code
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

            async def get(self, url, params):
                requests.append((url, params))
                if url == api_url:
                    return Response(429, {"error": "rate limited"})
                return Response(200, {
                    "features": [{
                        "geometry": {"coordinates": [-74.006, 40.7128]},
                        "properties": {
                            "name": "New York",
                            "city": "New York",
                            "state": "New York",
                            "country": "United States",
                            "countrycode": "us",
                            "extent": [-74.3, 40.4, -73.7, 40.9],
                        },
                    }],
                })

        with patch("app.services.location.httpx.AsyncClient", AsyncClient):
            resolver = NominatimLocationResolver(api_url=api_url)
            resolved = await resolver.resolve(location, "United States")
            cached = await NominatimLocationResolver(
                api_url=api_url
            ).resolve(location.upper(), "UNITED STATES")

        self.assertEqual([request[0] for request in requests], [
            api_url,
            "https://photon.komoot.io/api/",
        ])
        self.assertEqual(requests[1][1]["countrycode"], "US")
        self.assertEqual(resolved["city"], "New York")
        self.assertEqual(resolved["boundingbox"], [40.4, 40.9, -74.3, -73.7])
        self.assertEqual(cached, resolved)

    async def test_malformed_nominatim_response_falls_back_to_photon(self):
        location = "BuyerBridge malformed fallback, NY"
        api_url = "https://nominatim.example/search"
        cache_key = f"{api_url}|{location.casefold()}|united states"
        NominatimLocationResolver._cache.pop(cache_key, None)

        class Response:
            status_code = 200

            def __init__(self, body):
                self.body = body

            def json(self):
                if isinstance(self.body, Exception):
                    raise self.body
                return self.body

        class AsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def get(self, url, params):
                if url == api_url:
                    return Response(ValueError("invalid JSON"))
                return Response({
                    "features": [{
                        "geometry": {"coordinates": [-74.0, 40.7]},
                        "properties": {
                            "name": "New York",
                            "countrycode": "us",
                        },
                    }],
                })

        with patch("app.services.location.httpx.AsyncClient", AsyncClient):
            resolved = await NominatimLocationResolver(api_url=api_url).resolve(
                location,
                "United States",
            )

        self.assertEqual(resolved["latitude"], 40.7)
        self.assertEqual(resolved["longitude"], -74.0)
