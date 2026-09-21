import logging
import smtplib
from email.utils import parseaddr
from dataclasses import dataclass
from email.message import EmailMessage as MIMEEmailMessage
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 15
BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"
BREVO_TIMEOUT_SECONDS = 15


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


class BrevoEmailSender:
    """Sends through Brevo's transactional HTTPS API (works where SMTP ports
    are blocked). EMAIL_FROM must be a sender verified in Brevo. Errors carry
    only the status code and Brevo's message, never the API key."""

    def send(self, message: EmailMessage) -> None:
        _reject_header_injection(message.to_email, message.subject)

        name, address = parseaddr(settings.EMAIL_FROM)
        payload: dict = {
            "sender": {"email": address, **({"name": name} if name else {})},
            "to": [{"email": message.to_email}],
            "subject": message.subject,
            "textContent": message.body_text,
        }
        if message.body_html:
            payload["htmlContent"] = message.body_html

        response = httpx.post(
            BREVO_API_URL,
            json=payload,
            headers={
                "api-key": settings.BREVO_API_KEY or "",
                "accept": "application/json",
            },
            timeout=BREVO_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("message", "")
            except ValueError:
                detail = ""
            raise RuntimeError(f"Brevo API error {response.status_code}: {detail}")


class LoggingEmailSender:
    """Development fallback: never logs the body (may contain sensitive data)."""

    def send(self, message: EmailMessage) -> None:
        _reject_header_injection(message.to_email, message.subject)
        logger.info(
            "Email not sent (no BREVO_API_KEY or SMTP_HOST): to=%s subject=%s",
            message.to_email,
            message.subject,
        )


def get_email_sender() -> EmailSender:
    if settings.BREVO_API_KEY:
        return BrevoEmailSender()
    if settings.SMTP_HOST:
        return SMTPEmailSender()
    return LoggingEmailSender()
