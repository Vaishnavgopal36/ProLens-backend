import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from app.core.config import settings
from app.models.enums import OutboxStatus
from app.models.outbox import EmailOutbox
from app.repositories.base_repository import BaseRepository

STALE_PROCESSING_AFTER = timedelta(minutes=5)
MAX_BACKOFF_SECONDS = 3600
MAX_ERROR_LENGTH = 2000


def compute_backoff_seconds(attempts: int) -> int:
    exponent = max(attempts - 1, 0)
    return min(settings.OUTBOX_RETRY_BASE_SECONDS * 2**exponent, MAX_BACKOFF_SECONDS)


class OutboxRepository(BaseRepository[EmailOutbox]):
    model = EmailOutbox

    def claim_batch(self, limit: int) -> list[EmailOutbox]:
        """Lock due rows (SKIP LOCKED so workers never collide), mark them
        processing. Rows stuck in processing (crashed worker) are reclaimed."""
        now = datetime.now(timezone.utc)
        stale_before = now - STALE_PROCESSING_AFTER

        stmt = (
            select(EmailOutbox)
            .where(
                EmailOutbox.next_attempt_at <= now,
                or_(
                    EmailOutbox.status == OutboxStatus.pending,
                    (EmailOutbox.status == OutboxStatus.processing)
                    & (EmailOutbox.locked_at <= stale_before),
                ),
            )
            .order_by(EmailOutbox.next_attempt_at, EmailOutbox.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = list(self.db.scalars(stmt))

        for row in rows:
            row.status = OutboxStatus.processing
            row.locked_at = now
            row.updated_at = now
        self.db.flush()
        return rows

    def get_for_update(self, outbox_id: uuid.UUID) -> EmailOutbox | None:
        return self.db.scalar(
            select(EmailOutbox).where(EmailOutbox.id == outbox_id).with_for_update()
        )

    def mark_sent(self, row: EmailOutbox) -> None:
        now = datetime.now(timezone.utc)
        row.status = OutboxStatus.sent
        row.sent_at = now
        row.locked_at = None
        row.last_error = None
        row.updated_at = now
        self.db.flush()

    def mark_retry(self, row: EmailOutbox, error: str) -> None:
        now = datetime.now(timezone.utc)
        row.attempts += 1
        row.status = OutboxStatus.pending
        row.locked_at = None
        row.last_error = error[:MAX_ERROR_LENGTH]
        row.next_attempt_at = now + timedelta(
            seconds=compute_backoff_seconds(row.attempts)
        )
        row.updated_at = now
        self.db.flush()

    def mark_failed(self, row: EmailOutbox, error: str) -> None:
        now = datetime.now(timezone.utc)
        row.attempts += 1
        row.status = OutboxStatus.failed
        row.locked_at = None
        row.last_error = error[:MAX_ERROR_LENGTH]
        row.updated_at = now
        self.db.flush()

    def record_failure(self, row: EmailOutbox, error: str) -> None:
        """Retry with backoff, or fail permanently once attempts are exhausted."""
        if row.attempts + 1 >= row.max_attempts:
            self.mark_failed(row, error)
        else:
            self.mark_retry(row, error)
