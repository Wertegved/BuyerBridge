from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.config import settings


class EmailProvider:
    async def send(self, recipient: str, subject: str, message: str):
        raise NotImplementedError("Email provider must be implemented.")


class EmailService:
    def __init__(self, provider: EmailProvider | None = None):
        self.provider = provider

    async def send(self, recipient: str, subject: str, message: str):
        if self.provider is None:
            raise ValueError("No email provider configured.")
        return await self.provider.send(recipient=recipient, subject=subject, message=message)


class SMTPEmailProvider(EmailProvider):
    def __init__(self, smtp_settings=settings):
        self.smtp_settings = smtp_settings

    @property
    def missing_configuration(self) -> tuple[str, ...]:
        host = self.smtp_settings.SMTP_HOST.strip()
        username = self.smtp_settings.SMTP_USERNAME.strip()
        password = self.smtp_settings.SMTP_PASSWORD
        port = self.smtp_settings.SMTP_PORT
        missing = []
        if not host:
            missing.append("SMTP_HOST")
        if not username:
            missing.append("SMTP_USERNAME")
        if not password:
            missing.append("SMTP_PASSWORD")
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            missing.append("SMTP_PORT")
        return tuple(missing)

    @property
    def is_configured(self) -> bool:
        return not self.missing_configuration

    async def send(self, recipient: str, subject: str, message: str):
        if not self.is_configured:
            raise ValueError("SMTP is not configured.")

        sender = self.smtp_settings.SMTP_FROM or self.smtp_settings.SMTP_USERNAME
        sender_name = self.smtp_settings.SMTP_FROM_NAME
        message_email = EmailMessage()
        message_email["Subject"] = subject
        message_email["From"] = formataddr((sender_name, sender)) if sender_name else sender
        message_email["To"] = recipient
        message_email.set_content(message)

        await asyncio.to_thread(self._send_sync, message_email)
        return None

    def _send_sync(self, message: EmailMessage) -> None:
        with smtplib.SMTP(
            self.smtp_settings.SMTP_HOST,
            self.smtp_settings.SMTP_PORT,
            timeout=30,
        ) as smtp:
            if self.smtp_settings.SMTP_USE_TLS:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()

            if self.smtp_settings.SMTP_USERNAME and self.smtp_settings.SMTP_PASSWORD:
                smtp.login(
                    self.smtp_settings.SMTP_USERNAME,
                    self.smtp_settings.SMTP_PASSWORD,
                )

            smtp.send_message(message)
