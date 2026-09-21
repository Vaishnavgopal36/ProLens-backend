import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import OutboxStatus
from app.models.outbox import EmailOutbox


def enqueue_email(
    db: Session,
    organization_id: uuid.UUID,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> EmailOutbox:
    """Insert an outbox row in the caller's transaction. Flushes, never commits:
    the caller's commit makes the email job and the business change atomic."""
    row = EmailOutbox(
        organization_id=organization_id,
        to_email=to_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        status=OutboxStatus.pending,
        attempts=0,
        max_attempts=settings.OUTBOX_MAX_ATTEMPTS,
    )
    db.add(row)
    db.flush()
    return row
