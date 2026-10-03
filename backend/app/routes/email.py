from __future__ import annotations

import logging
import re
import smtplib
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.buyer import Buyer
from app.models.email import Email
from app.models.user import User
from app.routes.auth import get_current_user
from app.routes.buyers import get_buyers_for_user
from app.schemas.email import EmailRequest
from app.services.email_service import EmailService, SMTPEmailProvider

router = APIRouter(prefix="/api")
VALID_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
logger = logging.getLogger(__name__)


@router.post("/email/send")
async def send_email(
    payload: EmailRequest,
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
):
    if not payload.buyer_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select at least one buyer.",
        )

    try:
        buyer_ids = [int(buyer_id) for buyer_id in payload.buyer_ids]
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Every selected buyer must have a valid email address.",
        ) from exc

    owned_buyer_ids = {
        buyer.id for buyer in get_buyers_for_user(database, current_user.id)
    }
    buyers = database.execute(
        select(Buyer).where(
            Buyer.id.in_(set(buyer_ids)),
            Buyer.id.in_(owned_buyer_ids),
        )
    ).scalars().all()
    buyers_by_id = {buyer.id: buyer for buyer in buyers}
    if len(buyers_by_id) != len(set(buyer_ids)) or any(
        not isinstance(buyer.email, str) or not VALID_EMAIL_PATTERN.fullmatch(buyer.email.strip())
        for buyer in buyers
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Every selected buyer must have a valid email address.",
        )

    provider = SMTPEmailProvider()
    if not provider.is_configured:
        logger.warning(
            "SMTP provider unavailable; missing or invalid settings: %s",
            ", ".join(provider.missing_configuration),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMTP email is not configured. Check the server email settings.",
        )

    email_records = [
        Email(
            user_id=current_user.id,
            buyer_id=buyer_id,
            subject=payload.subject,
            message=payload.message,
            status="pending",
        )
        for buyer_id in buyer_ids
    ]
    database.add_all(email_records)
    database.commit()

    email_service = EmailService(provider)
    results = []
    for buyer_id, email_record in zip(buyer_ids, email_records):
        try:
            await email_service.send(
                recipient=buyers_by_id[buyer_id].email.strip(),
                subject=payload.subject,
                message=payload.message,
            )
        except smtplib.SMTPAuthenticationError:
            email_record.status = "failed"
            email_record.error_message = "SMTP authentication failed."
            results.append({
                "buyer_id": str(buyer_id),
                "status": "failed",
                "error": email_record.error_message,
            })
        except smtplib.SMTPException:
            email_record.status = "failed"
            email_record.error_message = "SMTP server rejected or failed the message."
            results.append({
                "buyer_id": str(buyer_id),
                "status": "failed",
                "error": email_record.error_message,
            })
        except (ConnectionError, TimeoutError, OSError):
            email_record.status = "failed"
            email_record.error_message = "Could not connect to or communicate with the SMTP server."
            results.append({
                "buyer_id": str(buyer_id),
                "status": "failed",
                "error": email_record.error_message,
            })
        else:
            email_record.status = "sent"
            email_record.sent_at = datetime.utcnow()
            email_record.provider_message_id = None
            email_record.error_message = None
            results.append({"buyer_id": str(buyer_id), "status": "sent", "error": None})

    database.commit()
    return {"results": results}
