from __future__ import annotations


class ContactEnrichmentProvider:
    async def enrich(self, business):
        raise NotImplementedError("Contact enrichment provider must be implemented.")


class ContactEnrichmentService:
    def __init__(self, provider: ContactEnrichmentProvider | None = None):
        self.provider = provider

    async def enrich(self, business):
        if self.provider is None:
            return business
        return await self.provider.enrich(business)
