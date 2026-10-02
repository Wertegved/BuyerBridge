from __future__ import annotations


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
