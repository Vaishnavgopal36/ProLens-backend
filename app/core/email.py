import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MIMEEmailMessage
from typing import Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class EmailMessage:
    to_email: str
    subject: str
    body_text: str
    body_html: str | None = None


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None: ...


def _reject_header_injection(*values: str) -> None:
    for value in values:
        if "\r" in value or "\n" in value:
            raise ValueError("Line breaks are not allowed in email headers")


class SMTPEmailSender:
    def send(self, message: EmailMessage) -> None:
        _reject_header_injection(message.to_email, message.subject)

        mime = MIMEEmailMessage()
        mime["From"] = settings.EMAIL_FROM
        mime["To"] = message.to_email
        mime["Subject"] = message.subject
        mime.set_content(message.body_text)
        if message.body_html:
            mime.add_alternative(message.body_html, subtype="html")

        with smtplib.SMTP(
            settings.SMTP_HOST, settings.SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS
        ) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls()
            if settings.SMTP_USERNAME:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")
            smtp.send_message(mime)


class LoggingEmailSender:
    """Development fallback: never logs the body (may contain sensitive data)."""

    def send(self, message: EmailMessage) -> None:
        _reject_header_injection(message.to_email, message.subject)
        logger.info(
            "Email not sent (SMTP_HOST unset): to=%s subject=%s",
            message.to_email,
            message.subject,
        )


def get_email_sender() -> EmailSender:
    if settings.SMTP_HOST:
        return SMTPEmailSender()
    return LoggingEmailSender()
