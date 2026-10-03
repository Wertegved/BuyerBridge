from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx


class ContactEnrichmentProvider:
    async def enrich(self, business: Any) -> Any:
        raise NotImplementedError(
            "Contact enrichment provider must be implemented."
        )


class FindymailContactEnrichment(ContactEnrichmentProvider):
    """
    Findymail-based contact enrichment.

    Only stores an email when Findymail actually returns one.
    Missing emails, API errors, missing API keys, and rate limits
    do not break the buyer search.
    """

    API_URL = "https://app.findymail.com/api/search/domain"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("FINDYMAIL_API_KEY")

    @staticmethod
    def _get_value(business: Any, key: str) -> Any:
        if isinstance(business, dict):
            return business.get(key)
        return getattr(business, key, None)

    @staticmethod
    def _set_value(business: Any, key: str, value: Any) -> Any:
        if isinstance(business, dict):
            business[key] = value
        else:
            try:
                setattr(business, key, value)
            except Exception:
                pass

        return business

    @staticmethod
    def _extract_domain(website: str | None) -> str | None:
        if not website:
            return None

        website = website.strip()

        if not website:
            return None

        # Add a scheme when the stored website is like:
        # example.com
        if not re.match(r"^https?://", website, re.IGNORECASE):
            website = f"https://{website}"

        try:
            parsed = urlparse(website)
            domain = parsed.netloc.lower().strip()

            # Remove credentials and port if present.
            domain = domain.split("@")[-1]
            domain = domain.split(":")[0]

            # Remove leading www.
            if domain.startswith("www."):
                domain = domain[4:]

            return domain or None

        except Exception:
            return None

    async def enrich(self, business: Any) -> Any:
        # Always preserve the original business when enrichment
        # cannot be performed.
        if not self.api_key:
            return business

        website = self._get_value(business, "website")
        domain = self._extract_domain(website)

        if not domain:
            return business

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "domain": domain,
            "roles": [
                "Owner",
                "Founder",
                "CEO",
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    self.API_URL,
                    headers=headers,
                    json=payload,
                )

            # Do not fail the buyer search because enrichment failed.
            if response.status_code != 200:
                return business

            data = response.json()

        except (httpx.HTTPError, ValueError, Exception):
            return business

        contact = data.get("contact")

        if not isinstance(contact, dict):
            return business

        email = contact.get("email")

        if not isinstance(email, str):
            return business

        email = email.strip().lower()

        # Basic validation so we never store malformed values.
        if not email or "@" not in email:
            return business

        self._set_value(business, "email", email)
        self._set_value(business, "email_available", True)
        self._set_value(business, "contact_source", "findymail")

        return business


class ContactEnrichmentService:
    def __init__(self, provider: ContactEnrichmentProvider | None = None):
        self.provider = provider

    async def enrich(self, business: Any) -> Any:
        if self.provider is None:
            return business

        return await self.provider.enrich(business)