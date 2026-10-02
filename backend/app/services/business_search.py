from __future__ import annotations


class BusinessSearchProvider:
    async def search(self, query: str, location: str, limit: int):
        raise NotImplementedError("Business search provider must be implemented.")


class BusinessSearchService:
    def __init__(self, provider: BusinessSearchProvider | None = None):
        self.provider = provider

    async def search(self, query: str, location: str, limit: int):
        if self.provider is None:
            raise ValueError("No business search provider configured.")
        return await self.provider.search(query=query, location=location, limit=limit)
