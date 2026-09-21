"""Outbox worker: `python -m app.worker`.

Runs as a system process, so it bypasses tenant RLS (same technique as
bypass_rls_for_pre_auth_lookup). Rows are claimed and committed as
`processing` first, the network send happens with no DB locks held, and the
result is recorded in a new short transaction.
"""

import logging
import signal
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from types import FrameType

from sqlalchemy.orm import Session

from app.api.deps import bypass_rls_for_pre_auth_lookup
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.email import EmailMessage, EmailSender, get_email_sender
from app.repositories.outbox_repository import OutboxRepository

logger = logging.getLogger("prolens.worker")

_shutdown = False


@dataclass(frozen=True)
class _Job:
    id: uuid.UUID
    message: EmailMessage


def _claim(session_factory: Callable[[], Session]) -> list[_Job]:
    session = session_factory()
    try:
        bypass_rls_for_pre_auth_lookup(session)
        rows = OutboxRepository(session).claim_batch(settings.OUTBOX_BATCH_SIZE)
        jobs = [
            _Job(
                id=row.id,
                message=EmailMessage(
                    to_email=row.to_email,
                    subject=row.subject,
                    body_text=row.body_text,
                    body_html=row.body_html,
                ),
            )
            for row in rows
        ]
        session.commit()
        return jobs
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _record(
    session_factory: Callable[[], Session],
    job_id: uuid.UUID,
    error: str | None,
) -> None:
    session = session_factory()
    try:
        bypass_rls_for_pre_auth_lookup(session)
        repo = OutboxRepository(session)
        row = repo.get_for_update(job_id)
        if row is not None:
            if error is None:
                repo.mark_sent(row)
            else:
                repo.record_failure(row, error)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def process_batch(
    session_factory: Callable[[], Session],
    sender: EmailSender,
) -> int:
    """Claim and deliver one batch. Returns the number of rows claimed."""
    jobs = _claim(session_factory)

    for job in jobs:
        error: str | None = None
        try:
            sender.send(job.message)
        except Exception as exc:  # one bad email must never stop the loop
            error = f"{type(exc).__name__}: {exc}"
            logger.warning("Email %s failed: %s", job.id, error)
        try:
            _record(session_factory, job.id, error)
        except Exception:
            # Row stays `processing` and is reclaimed after the stale timeout.
            logger.exception("Could not record result for email %s", job.id)
        else:
            if error is None:
                logger.info("Email %s sent", job.id)

    return len(jobs)


def _request_shutdown(signum: int, _frame: FrameType | None) -> None:
    global _shutdown
    logger.info("Signal %s received, shutting down after current batch", signum)
    _shutdown = True


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)

    sender = get_email_sender()
    logger.info("Outbox worker started (sender=%s)", type(sender).__name__)

    while not _shutdown:
        try:
            processed = process_batch(SessionLocal, sender)
        except Exception:
            logger.exception("Outbox batch failed")
            processed = 0
        if processed == 0 and not _shutdown:
            time.sleep(settings.OUTBOX_POLL_INTERVAL_SECONDS)

    logger.info("Outbox worker stopped")


if __name__ == "__main__":
    run()
