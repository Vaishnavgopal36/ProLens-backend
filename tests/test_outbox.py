import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.worker as worker
from app.core import email as email_mod
from app.core.config import settings
from app.core.email import (
    EmailMessage,
    LoggingEmailSender,
    BrevoEmailSender,
    SMTPEmailSender,
    get_email_sender,
)
from app.models.enums import OutboxStatus
from app.repositories.outbox_repository import (
    MAX_BACKOFF_SECONDS,
    MAX_ERROR_LENGTH,
    OutboxRepository,
    compute_backoff_seconds,
)
from app.services.email_templates import project_member_added
from app.services.outbox_service import enqueue_email


def test_enqueue_flushes_without_commit():
    db = MagicMock()
    org = uuid.uuid4()
    row = enqueue_email(db, org, "a@b.com", "Hi", "text", "<p>x</p>")
    db.add.assert_called_once_with(row)
    db.flush.assert_called_once()
    db.commit.assert_not_called()
    assert row.organization_id == org
    assert row.to_email == "a@b.com"
    assert row.status == OutboxStatus.pending
    assert row.attempts == 0
    assert row.max_attempts == settings.OUTBOX_MAX_ATTEMPTS


def test_template_escapes_everything():
    subject, text, html = project_member_added(
        "<b>Bob</b>", "<script>x</script>", "A&B", 'http://x/"><img>'
    )
    assert "<script>" not in html
    assert "<b>Bob</b>" not in html
    assert "&lt;script&gt;" in html
    assert "A&amp;B" in html
    assert '"><img>' not in html
    assert "<script>" in subject  # subjects are plain text, not HTML


def test_sender_selection(monkeypatch):
    monkeypatch.setattr(settings, "BREVO_API_KEY", None)
    monkeypatch.setattr(settings, "SMTP_HOST", None)
    assert isinstance(get_email_sender(), LoggingEmailSender)
    monkeypatch.setattr(settings, "BREVO_API_KEY", "k")
    assert isinstance(get_email_sender(), BrevoEmailSender)
    monkeypatch.setattr(settings, "BREVO_API_KEY", None)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    assert isinstance(get_email_sender(), SMTPEmailSender)


@pytest.mark.parametrize(
    "cls", [SMTPEmailSender, LoggingEmailSender, BrevoEmailSender]
)
@pytest.mark.parametrize(
    "to,subject", [("a@b.com\r\nBcc: x@y.z", "s"), ("a@b.com", "s\nBcc: x@y.z")]
)
def test_crlf_rejected(cls, to, subject):
    with pytest.raises(ValueError):
        cls().send(EmailMessage(to, subject, "body"))


def test_logging_sender_never_logs_body(caplog):
    with caplog.at_level("INFO", logger=email_mod.logger.name):
        LoggingEmailSender().send(EmailMessage("a@b.com", "Subj", "SECRET-BODY"))
    assert "a@b.com" in caplog.text and "Subj" in caplog.text
    assert "SECRET-BODY" not in caplog.text


def test_smtp_sender_uses_tls_and_login(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "h")
    monkeypatch.setattr(settings, "SMTP_USERNAME", "u")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "p")
    monkeypatch.setattr(settings, "SMTP_USE_TLS", True)
    smtp = MagicMock()
    smtp_cls = MagicMock()
    smtp_cls.return_value.__enter__.return_value = smtp
    monkeypatch.setattr(email_mod.smtplib, "SMTP", smtp_cls)
    SMTPEmailSender().send(EmailMessage("a@b.com", "S", "t", "<p>h</p>"))
    assert smtp_cls.call_args.kwargs["timeout"] == 15
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("u", "p")
    sent = smtp.send_message.call_args.args[0]
    assert sent.is_multipart()


def test_brevo_sender_posts_to_api(monkeypatch):
    monkeypatch.setattr(settings, "BREVO_API_KEY", "key-123")
    monkeypatch.setattr(settings, "EMAIL_FROM", "ProLens <hello@example.com>")
    post = MagicMock(return_value=MagicMock(status_code=201))
    monkeypatch.setattr(email_mod.httpx, "post", post)
    BrevoEmailSender().send(EmailMessage("a@b.com", "S", "t", "<p>h</p>"))
    assert post.call_args.args[0] == email_mod.BREVO_API_URL
    assert post.call_args.kwargs["headers"]["api-key"] == "key-123"
    body = post.call_args.kwargs["json"]
    assert body["sender"] == {"email": "hello@example.com", "name": "ProLens"}
    assert body["to"] == [{"email": "a@b.com"}]
    assert body["htmlContent"] == "<p>h</p>"


def test_brevo_error_hides_api_key(monkeypatch):
    monkeypatch.setattr(settings, "BREVO_API_KEY", "key-123")
    resp = MagicMock(status_code=401)
    resp.json.return_value = {"message": "Key not found"}
    monkeypatch.setattr(email_mod.httpx, "post", MagicMock(return_value=resp))
    with pytest.raises(RuntimeError) as exc:
        BrevoEmailSender().send(EmailMessage("a@b.com", "S", "t"))
    assert "401" in str(exc.value) and "key-123" not in str(exc.value)


def test_backoff(monkeypatch):
    monkeypatch.setattr(settings, "OUTBOX_RETRY_BASE_SECONDS", 30)
    assert compute_backoff_seconds(1) == 30
    assert compute_backoff_seconds(2) == 60
    assert compute_backoff_seconds(3) == 120
    assert compute_backoff_seconds(20) == MAX_BACKOFF_SECONDS


def _row(attempts=0, max_attempts=3):
    return SimpleNamespace(
        id=uuid.uuid4(),
        to_email="a@b.com",
        subject="s",
        body_text="t",
        body_html=None,
        status=OutboxStatus.processing,
        attempts=attempts,
        max_attempts=max_attempts,
        last_error=None,
        locked_at=datetime.now(timezone.utc),
        sent_at=None,
        next_attempt_at=None,
        updated_at=None,
    )


def test_repository_retry_and_failure_transitions():
    repo = OutboxRepository(MagicMock())
    row = _row(attempts=0, max_attempts=3)
    repo.record_failure(row, "x" * 5000)
    assert row.status == OutboxStatus.pending
    assert row.attempts == 1
    assert len(row.last_error) == MAX_ERROR_LENGTH
    assert row.next_attempt_at > datetime.now(timezone.utc)

    row = _row(attempts=2, max_attempts=3)
    repo.record_failure(row, "boom")
    assert row.status == OutboxStatus.failed
    assert row.attempts == 3


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.closed = False

    def execute(self, *a, **k):
        pass

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closed = True


class FakeRepo:
    rows: list = []
    by_id: dict = {}

    def __init__(self, session):
        pass

    def claim_batch(self, limit):
        return FakeRepo.rows

    def get_for_update(self, id_):
        return FakeRepo.by_id.get(id_)

    def mark_sent(self, row):
        row.status = OutboxStatus.sent

    def record_failure(self, row, error):
        OutboxRepository(MagicMock()).record_failure(row, error)


class FlakySender:
    def __init__(self, failing):
        self.failing = failing
        self.sent = []

    def send(self, message):
        if message.to_email in self.failing:
            raise RuntimeError("smtp down")
        self.sent.append(message.to_email)


def test_process_batch_success_retry_and_final_failure(monkeypatch):
    ok = _row()
    ok.to_email = "ok@x.com"
    retry = _row(attempts=0, max_attempts=3)
    retry.to_email = "retry@x.com"
    final = _row(attempts=2, max_attempts=3)
    final.to_email = "final@x.com"
    FakeRepo.rows = [ok, retry, final]
    FakeRepo.by_id = {r.id: r for r in FakeRepo.rows}
    monkeypatch.setattr(worker, "OutboxRepository", FakeRepo)

    sender = FlakySender({"retry@x.com", "final@x.com"})
    sessions = []

    def factory():
        s = FakeSession()
        sessions.append(s)
        return s

    assert worker.process_batch(factory, sender) == 3
    assert sender.sent == ["ok@x.com"]
    assert ok.status == OutboxStatus.sent
    assert retry.status == OutboxStatus.pending and retry.attempts == 1
    assert final.status == OutboxStatus.failed
    assert "smtp down" in final.last_error
    assert all(s.closed for s in sessions)


def test_process_batch_survives_record_error(monkeypatch):
    row = _row()
    FakeRepo.rows = [row, _row()]
    FakeRepo.by_id = {}
    monkeypatch.setattr(worker, "OutboxRepository", FakeRepo)

    def boom(self, row):
        raise RuntimeError("db down")

    monkeypatch.setattr(FakeRepo, "get_for_update", lambda self, i: boom(self, i))
    sender = FlakySender(set())
    assert worker.process_batch(FakeSession, sender) == 2
    assert len(sender.sent) == 2
