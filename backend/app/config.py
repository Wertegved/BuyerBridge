from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    APP_ENV: str = os.getenv("APP_ENV", "development")
    TEST_DATABASE_URL: str = os.getenv("TEST_DATABASE_URL", "sqlite:///./buyerbridge_test.db")
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/buyerbridge",
    )
    if APP_ENV == "test":
        DATABASE_URL = TEST_DATABASE_URL
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5500")

    BUSINESS_API_KEY: str = os.getenv("BUSINESS_API_KEY", "")
    BUSINESS_API_BASE_URL: str = os.getenv("BUSINESS_API_BASE_URL", "")

    CONTACT_API_KEY: str = os.getenv("CONTACT_API_KEY", "")
    CONTACT_API_BASE_URL: str = os.getenv("CONTACT_API_BASE_URL", "")

    EMAIL_API_KEY: str = os.getenv("EMAIL_API_KEY", "")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "")
    EMAIL_API_BASE_URL: str = os.getenv("EMAIL_API_BASE_URL", "")


settings = Settings()
