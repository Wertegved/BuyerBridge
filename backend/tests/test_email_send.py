from __future__ import annotations

import smtplib
import unittest
from datetime import datetime, timedelta
from email.message import EmailMessage
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database.tables import Base
from app.models.buyer import Buyer
from app.models.email import Email
from app.models.search import Search
from app.models.user import User
from app.routes.email import send_email
from app.schemas.email import EmailRequest
from app.services.email_service import SMTPEmailProvider


def make_request(buyer_ids: list[str]) -> EmailRequest:
    return EmailRequest(
        buyer_ids=buyer_ids,
        subject="A business introduction",
        message="Hello, we would like to discuss a possible partnership.",
    )


class FakeSMTP:
    instances = []
    failure = None
    fail_send_number = None
    send_count = 0

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.calls = []
        self.__class__.instances.append(self)
        if self.__class__.failure:
            raise self.__class__.failure

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self):
        self.calls.append("starttls")

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def send_message(self, message):
        self.__class__.send_count += 1
        if self.__class__.send_count == self.__class__.fail_send_number:
            raise smtplib.SMTPException("SMTP delivery rejected.")
        self.calls.append(message)


class EmailSendTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.database = Session(self.engine)
        self.user = User(
            name="BuyerBridge User",
            email="owner@example.com",
            password_hash="unused",
            is_active=True,
        )
        self.database.add(self.user)
        self.database.flush()
        self.base_time = datetime(2026, 1, 1)
        self.database.add(
            Search(
                user_id=self.user.id,
                product_category="Furniture",
                product_description="Commercial furniture for design projects.",
                buyer_type="Interior Designers",
                location="New York",
                country="United States",
                result_count=0,
                created_at=self.base_time,
            )
        )
        self.database.flush()
        self.buyers = []
        self.fake_smtp()

    def tearDown(self):
        self.database.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def fake_smtp(self):
        self.smtp_patch = patch("app.services.email_service.smtplib.SMTP", FakeSMTP)
        self.smtp_patch.start()
        self.addCleanup(self.smtp_patch.stop)
        FakeSMTP.instances = []
        FakeSMTP.failure = None
        FakeSMTP.fail_send_number = None
        FakeSMTP.send_count = 0
        for name, value in (
            ("SMTP_HOST", "smtp.example.test"),
            ("SMTP_PORT", 587),
            ("SMTP_USERNAME", "sender@example.test"),
            ("SMTP_PASSWORD", "secret-test-password"),
            ("SMTP_USE_TLS", True),
            ("SMTP_FROM", ""),
            ("SMTP_FROM_NAME", "BuyerBridge Test"),
        ):
            self.enterContext(patch.object(settings, name, value))

    def test_settings_load_smtp_environment_and_provider_is_configured(self):
        with (
            patch.object(settings, "SMTP_HOST", "smtp.gmail.com"),
            patch.object(settings, "SMTP_PORT", 587),
            patch.object(settings, "SMTP_USERNAME", "sender@example.test"),
            patch.object(settings, "SMTP_PASSWORD", "test-only-password"),
            patch.object(settings, "SMTP_USE_TLS", True),
            patch.object(settings, "SMTP_FROM", ""),
            patch.object(settings, "SMTP_FROM_NAME", "BuyerBridge Test"),
        ):
            provider = SMTPEmailProvider(settings)
            self.assertTrue(provider.is_configured)
            self.assertEqual(provider.smtp_settings.SMTP_HOST, "smtp.gmail.com")
            self.assertEqual(provider.smtp_settings.SMTP_PORT, 587)
            self.assertTrue(provider.smtp_settings.SMTP_USE_TLS)

    def test_missing_smtp_password_marks_provider_unavailable(self):
        with patch.object(settings, "SMTP_PASSWORD", ""):
            provider = SMTPEmailProvider(settings)
            self.assertFalse(provider.is_configured)
            self.assertEqual(provider.missing_configuration, ("SMTP_PASSWORD",))

    def test_default_provider_instance_uses_application_settings(self):
        with (
            patch.object(settings, "SMTP_HOST", "smtp.gmail.com"),
            patch.object(settings, "SMTP_PORT", 587),
            patch.object(settings, "SMTP_USERNAME", "sender@example.test"),
            patch.object(settings, "SMTP_PASSWORD", "test-only-password"),
        ):
            provider = SMTPEmailProvider()
            self.assertIs(provider.smtp_settings, settings)
            self.assertTrue(provider.is_configured)

    def add_buyer(self, email: str | None):
        buyer = Buyer(
            business_name=f"Business {len(self.buyers) + 1}",
            email=email,
            email_available=bool(email),
            created_at=self.base_time + timedelta(minutes=len(self.buyers) + 1),
        )
        self.database.add(buyer)
        self.buyers.append(buyer)
        self.database.flush()
        search = self.database.execute(select(Search)).scalar_one()
        search.result_count = len(self.buyers)
        self.database.commit()
        return buyer

    async def send(self, buyers):
        return await send_email(
            make_request([str(buyer.id) for buyer in buyers]),
            current_user=self.user,
            database=self.database,
        )

    async def test_one_successful_email_creates_sent_record(self):
        buyer = self.add_buyer("one@example.com")

        response = await self.send([buyer])

        self.assertEqual(response["results"], [{"buyer_id": str(buyer.id), "status": "sent", "error": None}])
        records = self.database.execute(select(Email)).scalars().all()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].status, "sent")
        self.assertIsNotNone(records[0].sent_at)
        self.assertIsNone(records[0].provider_message_id)
        self.assertEqual(FakeSMTP.instances[0].calls[-1]["To"], "one@example.com")

    async def test_multiple_successful_emails_create_one_record_per_buyer(self):
        first = self.add_buyer("one@example.com")
        second = self.add_buyer("two@example.com")

        response = await self.send([first, second])

        self.assertEqual([result["status"] for result in response["results"]], ["sent", "sent"])
        self.assertEqual(len(FakeSMTP.instances), 2)
        records = self.database.execute(select(Email).order_by(Email.id)).scalars().all()
        self.assertEqual([record.buyer_id for record in records], [first.id, second.id])
        self.assertTrue(all(record.status == "sent" and record.sent_at for record in records))

    async def test_authentication_failure_is_persisted_as_safe_failed_record(self):
        buyer = self.add_buyer("one@example.com")
        FakeSMTP.failure = smtplib.SMTPAuthenticationError(535, b"secret-test-password rejected")

        response = await self.send([buyer])

        record = self.database.execute(select(Email)).scalar_one()
        self.assertEqual(response["results"][0]["status"], "failed")
        self.assertEqual(record.status, "failed")
        self.assertEqual(record.error_message, "SMTP authentication failed.")
        self.assertNotIn("secret-test-password", record.error_message)
        self.assertIsNone(record.sent_at)

    async def test_connection_failure_is_persisted_as_failed_record(self):
        buyer = self.add_buyer("one@example.com")
        FakeSMTP.failure = ConnectionError("connection failed")

        response = await self.send([buyer])

        record = self.database.execute(select(Email)).scalar_one()
        self.assertEqual(response["results"][0]["status"], "failed")
        self.assertEqual(record.status, "failed")
        self.assertEqual(
            record.error_message,
            "Could not connect to or communicate with the SMTP server.",
        )
        self.assertIsNone(record.sent_at)

    async def test_partial_smtp_failure_is_reported_for_each_recipient(self):
        first = self.add_buyer("one@example.com")
        second = self.add_buyer("two@example.com")
        FakeSMTP.fail_send_number = 1

        response = await self.send([first, second])

        self.assertEqual(
            [result["status"] for result in response["results"]],
            ["failed", "sent"],
        )
        records = self.database.execute(select(Email).order_by(Email.id)).scalars().all()
        self.assertEqual([record.status for record in records], ["failed", "sent"])
        self.assertEqual(
            records[0].error_message,
            "SMTP server rejected or failed the message.",
        )
        self.assertIsNotNone(records[1].sent_at)

    async def test_missing_email_rejects_entire_request_before_smtp(self):
        valid = self.add_buyer("valid@example.com")
        missing = self.add_buyer(None)

        with self.assertRaises(HTTPException) as raised:
            await self.send([valid, missing])

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("Every selected buyer must have a valid email address", raised.exception.detail)
        self.assertEqual(FakeSMTP.instances, [])
        self.assertEqual(self.database.execute(select(Email)).scalars().all(), [])

    async def test_buyer_from_another_user_is_rejected_before_smtp(self):
        other_user = User(
            name="Other User",
            email="other@example.com",
            password_hash="unused",
            is_active=True,
        )
        self.database.add(other_user)
        self.database.flush()
        other_search = Search(
            user_id=other_user.id,
            product_category="Furniture",
            product_description="Commercial furniture for design projects.",
            buyer_type="Interior Designers",
            location="New York",
            country="United States",
            result_count=1,
            created_at=self.base_time + timedelta(days=1),
        )
        other_buyer = Buyer(
            business_name="Other User Business",
            email="other-business@example.com",
            created_at=self.base_time + timedelta(days=1, minutes=1),
        )
        self.database.add_all([other_search, other_buyer])
        self.database.commit()

        with self.assertRaises(HTTPException) as raised:
            await self.send([other_buyer])

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(FakeSMTP.instances, [])
        self.assertEqual(self.database.execute(select(Email)).scalars().all(), [])

    async def test_provider_uses_starttls_login_and_formatted_sender(self):
        provider = SMTPEmailProvider()
        await provider.send("recipient@example.com", "Subject", "Body")

        calls = FakeSMTP.instances[0].calls
        self.assertEqual(calls[:4], [
            "ehlo",
            "starttls",
            "ehlo",
            ("login", "sender@example.test", "secret-test-password"),
        ])
        message = calls[4]
        self.assertIsInstance(message, EmailMessage)
        self.assertEqual(message["From"], "BuyerBridge Test <sender@example.test>")
        self.assertEqual(message["To"], "recipient@example.com")
        self.assertEqual(message.get_content(), "Body\n")
