import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.core.exception import AppException
from app.models.enums import UserRole
from app.schemas.designation import DesignationCreate, DesignationUpdate
from app.schemas.organization import OrganizationCreate, OrganizationUpdate
from app.services.designation_service import DesignationService
from tests.conftest import ORG_ID, make_user


def _svc(existing=None, assigned=0, found=None):
    svc = DesignationService(MagicMock())
    svc.designations = MagicMock()
    svc.designations.get_active_by_name.return_value = existing
    svc.designations.count_assigned_users.return_value = assigned
    svc.designations.get_active_by_id.return_value = found
    svc.designations.add.side_effect = lambda d: d
    return svc


def test_duplicate_active_designation_name_is_409():
    admin = make_user(UserRole.admin)
    with pytest.raises(AppException) as exc:
        _svc(existing=object()).create_designation(admin, DesignationCreate(name="Dev"))
    assert exc.value.status_code == 409


def test_create_designation_ok():
    admin = make_user(UserRole.admin)
    assert (
        _svc().create_designation(admin, DesignationCreate(name=" Dev ")).name == "Dev"
    )


def test_rename_to_existing_name_is_409():
    admin = make_user(UserRole.admin)
    found = SimpleNamespace(id=uuid.uuid4(), organization_id=ORG_ID, name="A")
    with pytest.raises(AppException) as exc:
        _svc(existing=object(), found=found).update_designation(
            admin, found.id, DesignationUpdate(name="B")
        )
    assert exc.value.status_code == 409


def test_delete_assigned_designation_is_409():
    admin = make_user(UserRole.admin)
    found = SimpleNamespace(id=uuid.uuid4(), organization_id=ORG_ID, deleted_at=None)
    with pytest.raises(AppException) as exc:
        _svc(assigned=2, found=found).delete_designation(admin, found.id)
    assert exc.value.status_code == 409
    assert found.deleted_at is None


def test_designation_name_bounds_and_null():
    for bad in ("", "x" * 101):
        with pytest.raises(ValidationError):
            DesignationCreate(name=bad)
    with pytest.raises(ValidationError):
        DesignationUpdate.model_validate({"name": None})


def test_organization_domain_normalised_and_validated():
    org = OrganizationCreate(name="Acme", domain="  Acme.EXAMPLE.com ")
    assert org.domain == "acme.example.com"
    for bad in ("nodots", "bad_domain.com", "-a.com", "a..com"):
        with pytest.raises(ValidationError):
            OrganizationCreate(name="Acme", domain=bad)


def test_organization_admin_password_policy():
    with pytest.raises(ValidationError):
        OrganizationCreate(
            name="A", domain="a.com", admin_email="x@a.com", admin_password="short"
        )


def test_organization_update_rejects_nulls():
    for field in ("name", "status"):
        with pytest.raises(ValidationError):
            OrganizationUpdate.model_validate({field: None})
    assert OrganizationUpdate.model_validate({}).model_fields_set == set()


def test_list_endpoints_accept_pagination(make_client):
    client = make_client(UserRole.super_admin)
    assert client.get("/organizations?limit=5&offset=0").status_code == 200
    assert client.get("/organizations?limit=0").status_code == 422
    assert client.get("/designations?limit=5").status_code == 200
