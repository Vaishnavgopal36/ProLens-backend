import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import Response
from pydantic import ValidationError

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.cookies import clear_auth_cookies, set_auth_cookies
from app.core.exception import (
    AppException,
    InactiveAccountError,
    InvalidCredentialsAuthError,
    InvalidCredentialsError,
)
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.enums import OrgStatus, UserRole, UserStatus
from app.repositories.session_repository import SessionRepository
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserCreate
from app.services.auth_service import AuthService, is_account_usable
from tests.conftest import ORG_ID


def _user(**kw):
    base = dict(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        role=UserRole.employee,
        status=UserStatus.active,
        deleted_at=None,
        password_hash=hash_password("correct-horse"),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _org(**kw):
    base = dict(id=ORG_ID, deleted_at=None, status=OrgStatus.active)
    base.update(kw)
    return SimpleNamespace(**base)


# --- rate limiter -----------------------------------------------------------


def test_rate_limiter_blocks_after_max_attempts_and_resets(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("app.core.rate_limit.time.monotonic", lambda: now[0])
    limiter = SlidingWindowRateLimiter(max_attempts=2, window_seconds=60)

    limiter.check("k")
    limiter.record("k")
    limiter.record("k")
    with pytest.raises(AppException) as exc:
        limiter.check("k")
    assert exc.value.status_code == 429
    assert exc.value.status_message == "Too Many Requests"

    limiter.check("other")  # keys are independent
    now[0] += 61  # window slides past the recorded hits
    limiter.check("k")

    limiter.record("k")
    limiter.record("k")
    limiter.reset("k")
    limiter.check("k")


# --- cookies ----------------------------------------------------------------


def _cookies(response: Response) -> list[str]:
    return [v.decode() for k, v in response.raw_headers if k == b"set-cookie"]


def test_refresh_cookie_path_reaches_logout_and_max_ages_from_settings():
    response = Response()
    set_auth_cookies(response, TokenResponse(access_token="a", refresh_token="r"))
    cookies = _cookies(response)

    access = next(c for c in cookies if c.startswith("access_token=a"))
    refresh = next(c for c in cookies if c.startswith("refresh_token=r"))
    assert f"Max-Age={settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60}" in access
    assert "Path=/auth;" in refresh + ";"
    assert "Path=/auth/refresh" not in refresh
    assert f"Max-Age={settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400}" in refresh


def test_logout_clears_refresh_cookie_on_both_paths():
    response = Response()
    clear_auth_cookies(response)
    joined = " ".join(_cookies(response))
    assert "Path=/auth;" in joined + ";"
    assert "Path=/auth/refresh" in joined
    assert "access_token=" in joined


# --- session lifecycle ------------------------------------------------------


def test_logout_revokes_session():
    db = MagicMock()
    session = SimpleNamespace(
        revoked_at=None, expires_at=datetime.now(timezone.utc) + timedelta(days=1)
    )
    db.scalar.return_value = session
    service = AuthService(db)

    service.logout("some-refresh-token")

    assert session.revoked_at is not None
    db.commit.assert_not_called()  # routes commit, services never do


def test_refresh_rejected_when_org_suspended_and_session_revoked():
    db = MagicMock()
    user = _user()
    session = SimpleNamespace(
        user_id=user.id,
        revoked_at=None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db.scalar.return_value = session
    db.get.side_effect = lambda model, _id: (
        user if model.__name__ == "User" else _org(status=OrgStatus.suspended)
    )
    from app.core.exception import InvalidRefreshTokenError

    with pytest.raises(InvalidRefreshTokenError):
        AuthService(db).refresh("token")
    assert session.revoked_at is not None


def test_revoke_all_for_user_issues_update():
    db = MagicMock()
    SessionRepository(db).revoke_all_for_user(uuid.uuid4())
    db.execute.assert_called_once()


def test_login_runs_dummy_verify_for_unknown_user(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.services.auth_service.verify_dummy_password", lambda p: calls.append(p)
    )
    db = MagicMock()
    db.scalar.return_value = None
    with pytest.raises(InvalidCredentialsError):
        AuthService(db).login("nobody@example.com", "whatever12")
    assert calls == ["whatever12"]


def test_login_rejects_suspended_and_deleted_users():
    db = MagicMock()
    db.get.return_value = _org()
    db.scalar.return_value = _user(status=UserStatus.suspended)
    with pytest.raises(InactiveAccountError):
        AuthService(db).login("a@example.com", "correct-horse")

    db.scalar.return_value = _user(deleted_at=datetime.now(timezone.utc))
    with pytest.raises(InvalidCredentialsError):
        AuthService(db).login("a@example.com", "correct-horse")

    db.scalar.return_value = _user()
    db.get.return_value = _org(status=OrgStatus.suspended)
    with pytest.raises(InactiveAccountError):
        AuthService(db).login("a@example.com", "correct-horse")


def test_verify_password_tolerates_malformed_hash():
    assert verify_password("x", "not-a-bcrypt-hash") is False


def test_hash_refresh_token_is_stable():
    assert hash_refresh_token("t") == hash_refresh_token("t")


# --- get_current_user -------------------------------------------------------


def _call_get_current_user(user, org):
    token = create_access_token(user.id, user.organization_id)
    request = SimpleNamespace(cookies={"access_token": token})
    db = MagicMock()
    db.get.side_effect = lambda model, _id: user if model.__name__ == "User" else org
    return get_current_user(request, db)


def test_get_current_user_accepts_active_user():
    user = _user()
    assert _call_get_current_user(user, _org()) is user


@pytest.mark.parametrize(
    "user_kw, org",
    [
        (dict(deleted_at=datetime.now(timezone.utc)), _org()),
        (dict(status=UserStatus.suspended), _org()),
        (dict(status=UserStatus.invited), _org()),
        ({}, _org(deleted_at=datetime.now(timezone.utc))),
        ({}, _org(status=OrgStatus.suspended)),
        ({}, None),
    ],
)
def test_get_current_user_rejects_unusable_accounts(user_kw, org):
    with pytest.raises(InvalidCredentialsAuthError):
        _call_get_current_user(_user(**user_kw), org)


def test_super_admin_without_org_is_exempt_from_org_check():
    user = _user(role=UserRole.super_admin, organization_id=None)
    assert is_account_usable(user, None) is True


# --- password policy --------------------------------------------------------


def _create(**kw):
    data = dict(email="A@Example.com", password="longenough1", role=UserRole.admin)
    data.update(kw)
    return UserCreate(**data)


def test_password_policy_and_email_normalisation():
    assert _create().email == "a@example.com"
    with pytest.raises(ValidationError):
        _create(password="x" * (settings.PASSWORD_MIN_LENGTH - 1))
    with pytest.raises(ValidationError):
        _create(password="x" * 73)
    with pytest.raises(ValidationError):
        _create(password="é" * 40)  # 80 bytes


def test_login_request_lowercases_email():
    assert (
        LoginRequest(email="Bob@Example.COM", password="p").email == "bob@example.com"
    )
