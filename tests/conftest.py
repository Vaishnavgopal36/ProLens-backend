import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.database import get_db
from app.main import app
from app.models.enums import UserRole

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def make_user(role: UserRole = UserRole.employee, organization_id=ORG_ID, **extra):
    return SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=organization_id,
        role=role,
        status="active",
        email="user@example.com",
        deleted_at=None,
        **extra,
    )


@pytest.fixture
def db():
    """A stand-in Session: queries return empty results unless a test overrides."""
    session = MagicMock()
    session.scalars.return_value = []
    session.scalar.return_value = None
    session.get.return_value = None
    return session


@pytest.fixture
def make_client(db):
    """make_client(role) -> TestClient authenticated as a stub user of that role."""

    def _make(role: UserRole = UserRole.employee, **user_extra):
        user = make_user(role, **user_extra)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app, raise_server_exceptions=False)
        client.user = user
        return client

    yield _make
    app.dependency_overrides.clear()
