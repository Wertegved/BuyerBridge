from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)


class Settings:
    APP_ENV: str = os.getenv("APP_ENV", "development")
    TEST_DATABASE_URL: str = os.getenv("TEST_DATABASE_URL", "sqlite:///./buyerbridge_test.db")
    DEFAULT_DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/buyerbridge"
    DATABASE_URL: str = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

    if APP_ENV == "test" and not os.getenv("DATABASE_URL"):
        DATABASE_URL = TEST_DATABASE_URL

    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5500")
    SESSION_COOKIE_NAME: str = os.getenv("SESSION_COOKIE_NAME", "buyerbridge_session")
    SESSION_EXPIRE_MINUTES: int = int(os.getenv("SESSION_EXPIRE_MINUTES", "30"))
    SESSION_COOKIE_SECURE: bool = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    SESSION_COOKIE_SAME_SITE: str = os.getenv("SESSION_COOKIE_SAME_SITE", "lax")

    OVERPASS_API_URL: str = os.getenv("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter")
    OVERPASS_USER_AGENT: str = os.getenv("OVERPASS_USER_AGENT", "BuyerBridge/1.0")
    GEOCODING_API_URL: str = os.getenv("GEOCODING_API_URL", "https://nominatim.openstreetmap.org/search")
    GEOCODING_USER_AGENT: str = os.getenv("GEOCODING_USER_AGENT", "BuyerBridge/1.0")

    BUSINESS_API_KEY: str = os.getenv("BUSINESS_API_KEY", "")
    BUSINESS_API_BASE_URL: str = os.getenv("BUSINESS_API_BASE_URL", "")

    CONTACT_API_KEY: str = os.getenv("CONTACT_API_KEY", "")
    CONTACT_API_BASE_URL: str = os.getenv("CONTACT_API_BASE_URL", "")

    EMAIL_API_KEY: str = os.getenv("EMAIL_API_KEY", "")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "")
    EMAIL_API_BASE_URL: str = os.getenv("EMAIL_API_BASE_URL", "")
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    SMTP_FROM: str = os.getenv("SMTP_FROM", "")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "BuyerBridge")


settings = Settings()
