from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


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
    COMPANY_API_URL = "https://app.findymail.com/api/search/company"

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

        if not website or any(character.isspace() for character in website):
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

            if "." not in domain or domain.startswith(".") or domain.endswith("."):
                return None
            return domain

        except Exception:
            return None

    @classmethod
    def _extract_returned_domain(cls, data: Any) -> str | None:
        if not isinstance(data, dict):
            return None

        candidates = [data.get("domain"), data.get("website"), data.get("url")]
        company = data.get("company")
        if isinstance(company, dict):
            candidates.extend([company.get("domain"), company.get("website"), company.get("url")])
        for candidate in candidates:
            if isinstance(candidate, str):
                domain = cls._extract_domain(candidate)
                if domain:
                    return domain
        return None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _post_json(self, url: str, payload: dict[str, Any]) -> Any:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(url, headers=self._headers(), json=payload)
            if response.status_code != 200:
                return None
            return response.json()
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
            business_name = self._get_value(business, "business_name")
            if not isinstance(business_name, str) or not business_name.strip():
                return business

            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    company_response = await client.post(
                        self.COMPANY_API_URL,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                        json={"name": business_name.strip()},
                    )
                if company_response.status_code != 200:
                    return business
                domain = self._extract_returned_domain(company_response.json())
            except Exception:
                return business

            if not domain:
                return business
            self._set_value(business, "website", f"https://{domain}")

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
        logger.info(
            "Findymail contact lookup for %s using domain %s",
            self._get_value(business, "business_name") or "Business name unavailable",
            domain,
        )

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

        try:
            contacts = data.get("contacts") if isinstance(data, dict) else None
            contact = (
                contacts[0]
                if isinstance(contacts, list) and contacts
                else data.get("contact") if isinstance(data, dict) else None
            )
            if not isinstance(contact, dict):
                return business

            email = contact.get("email")
            if not isinstance(email, str):
                return business

            email = email.strip().lower()
            if not email or "@" not in email:
                return business

            self._set_value(business, "email", email)
            self._set_value(business, "email_available", True)
            self._set_value(business, "contact_source", "findymail")
            logger.info(
                "Findymail returned an email for %s",
                self._get_value(business, "business_name") or "Business name unavailable",
            )
        except Exception:
            return business

        return business


class ContactEnrichmentService:
    def __init__(self, provider: ContactEnrichmentProvider | None = None):
        self.provider = provider

    async def enrich(self, business: Any) -> Any:
        if self.provider is None:
            return business

        return await self.provider.enrich(business)