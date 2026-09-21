import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.exception import (
    AppException,
    CannotDeleteLastAdminError,
    DesignationNotFoundError,
    FieldNotEditableError,
    InsufficientPermissionError,
    InvalidRoleAssignmentError,
)
from app.core.security import hash_password
from app.models.enums import UserRole, UserStatus
from app.schemas.user import UserCreate, UserUpdate
from app.services.user_service import UserService
from tests.conftest import ORG_ID

DESIGNATION_ID = uuid.uuid4()


def _u(role=UserRole.employee, org=ORG_ID, **kw):
    base = dict(
        id=uuid.uuid4(),
        organization_id=org,
        role=role,
        status=UserStatus.active,
        deleted_at=None,
        designation_id=DESIGNATION_ID,
        first_name="A",
        last_name="B",
        password_hash=hash_password("old-password"),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _service(target=None, admins_left=1, designation_org=ORG_ID):
    svc = UserService(MagicMock())
    svc.users = MagicMock()
    svc.users.get_active_by_id.return_value = target
    svc.users.count_active_admins.return_value = admins_left
    svc.users.get_by_email.return_value = None
    svc.users.add.side_effect = lambda u: u
    svc.designations = MagicMock()
    svc.designations.get_active_by_id.return_value = SimpleNamespace(
        organization_id=designation_org
    )
    svc.organizations = MagicMock()
    svc.sessions = MagicMock()
    return svc


def _update(svc, caller, target, **fields):
    return svc.update_user(caller, target.id, UserUpdate(**fields))


def test_employee_cannot_edit_other_user():
    caller, target = _u(), _u()
    with pytest.raises(InsufficientPermissionError):
        _update(_service(target), caller, target, first_name="x")


def test_manager_cannot_edit_other_user():
    caller, target = _u(UserRole.manager), _u()
    with pytest.raises(InsufficientPermissionError):
        _update(_service(target), caller, target, first_name="x")


@pytest.mark.parametrize("role", [UserRole.employee, UserRole.manager])
@pytest.mark.parametrize(
    "fields",
    [
        {"role": UserRole.admin},
        {"status": UserStatus.suspended},
        {"designation_id": uuid.uuid4()},
    ],
)
def test_self_edit_of_privileged_fields_forbidden(role, fields):
    me = _u(role)
    with pytest.raises(FieldNotEditableError):
        _update(_service(me), me, me, **fields)


def test_employee_can_edit_own_name():
    me = _u()
    assert _update(_service(me), me, me, first_name="New").first_name == "New"


def test_self_password_change_requires_correct_current_password():
    me = _u()
    svc = _service(me)
    with pytest.raises(AppException) as exc:
        _update(svc, me, me, password="new-password1")
    assert exc.value.status_code == 403
    with pytest.raises(AppException):
        _update(svc, me, me, password="new-password1", current_password="wrong")

    _update(svc, me, me, password="new-password1", current_password="old-password")
    assert me.password_hash != hash_password("x")
    svc.sessions.revoke_all_for_user.assert_called_once_with(me.id)


def test_admin_cannot_change_own_role_or_status():
    me = _u(UserRole.admin, designation_id=None)
    svc = _service(me)
    with pytest.raises(FieldNotEditableError):
        _update(svc, me, me, role=UserRole.manager)
    with pytest.raises(FieldNotEditableError):
        _update(svc, me, me, status=UserStatus.suspended)


def test_admin_cannot_touch_super_admin_or_assign_it():
    admin = _u(UserRole.admin)
    sa = _u(UserRole.super_admin, org=None)
    with pytest.raises(InsufficientPermissionError):
        _update(_service(sa), admin, sa, status=UserStatus.suspended)
    target = _u(UserRole.manager)
    with pytest.raises(InvalidRoleAssignmentError):
        _update(_service(target), admin, target, role=UserRole.super_admin)


def test_admin_can_edit_employee_in_org():
    admin, target = _u(UserRole.admin), _u()
    _update(_service(target), admin, target, status=UserStatus.suspended)
    assert target.status == UserStatus.suspended


def test_last_admin_cannot_be_demoted_or_suspended_by_super_admin():
    sa = _u(UserRole.super_admin, org=None)
    last = _u(UserRole.admin, designation_id=None)
    svc = _service(last, admins_left=0)
    with pytest.raises(CannotDeleteLastAdminError):
        _update(svc, sa, last, role=UserRole.manager)
    with pytest.raises(CannotDeleteLastAdminError):
        _update(svc, sa, last, status=UserStatus.suspended)


def test_admin_demotion_allowed_when_another_admin_remains():
    sa = _u(UserRole.super_admin, org=None)
    adm = _u(UserRole.admin)
    _update(_service(adm, admins_left=1), sa, adm, role=UserRole.manager)
    assert adm.role == UserRole.manager


def test_delete_last_admin_rejected_and_sessions_revoked_on_delete():
    sa = _u(UserRole.super_admin, org=None)
    last = _u(UserRole.admin, designation_id=None)
    with pytest.raises(CannotDeleteLastAdminError):
        _service(last, admins_left=0).delete_user(sa, last.id)

    victim = _u()
    svc = _service(victim)
    svc.delete_user(sa, victim.id)
    assert victim.deleted_at is not None
    svc.sessions.revoke_all_for_user.assert_called_once_with(victim.id)


def test_role_employee_requires_designation():
    sa = _u(UserRole.super_admin, org=None)
    target = _u(UserRole.manager, designation_id=None)
    with pytest.raises(AppException) as exc:
        _update(_service(target), sa, target, role=UserRole.employee)
    assert exc.value.status_code == 422


def test_designation_must_belong_to_target_org():
    sa = _u(UserRole.super_admin, org=None)
    target = _u()
    svc = _service(target, designation_org=uuid.uuid4())
    with pytest.raises(DesignationNotFoundError):
        _update(svc, sa, target, designation_id=uuid.uuid4())


def test_create_employee_without_designation_is_422_and_wrong_org_designation_404():
    admin = _u(UserRole.admin)
    payload = dict(
        email="n@example.com", password="longenough1", role=UserRole.employee
    )
    with pytest.raises(AppException) as exc:
        _service().create_user(admin, UserCreate(**payload))
    assert exc.value.status_code == 422

    svc = _service(designation_org=uuid.uuid4())
    with pytest.raises(DesignationNotFoundError):
        svc.create_user(admin, UserCreate(**payload, designation_id=uuid.uuid4()))


def test_create_user_lowercases_email():
    admin = _u(UserRole.admin)
    user = _service().create_user(
        admin,
        UserCreate(
            email="Mixed@Example.com", password="longenough1", role=UserRole.admin
        ),
    )
    assert user.email == "mixed@example.com"


def test_update_rejects_null_role_and_password():
    with pytest.raises(ValueError):
        UserUpdate.model_validate({"role": None})
    with pytest.raises(ValueError):
        UserUpdate.model_validate({"password": None})


def test_employee_patch_other_user_route_is_403(make_client, db):
    client = make_client(UserRole.employee)
    response = client.patch(f"/users/{uuid.uuid4()}", json={"role": "admin"})
    assert response.status_code in (403, 404)
