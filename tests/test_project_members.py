import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.api.pagination import Pagination
from app.core.exception import (
    ProjectMemberAlreadyExistsError,
    ProjectMemberMutationForbiddenError,
    ProjectNotFoundError,
    UserNotFoundError,
)
from app.models.enums import UserRole, UserStatus
from app.models.outbox import EmailOutbox
from app.schemas.project_member import ProjectMemberCreate
from app.services.project_member_service import ProjectMemberService

ORG = uuid.uuid4()


def user(role=UserRole.employee, status=UserStatus.active, org=ORG, **kw):
    return SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=org,
        role=role,
        status=status,
        email=f"{uuid.uuid4().hex[:6]}@example.com",
        first_name="First",
        last_name="Last",
        deleted_at=None,
        **kw,
    )


def make_service(project="default", target=None, existing=None, is_member=True):
    db = MagicMock()
    svc = ProjectMemberService(db)
    if project == "default":
        project = SimpleNamespace(id=uuid.uuid4(), name="Apollo", organization_id=ORG)
    svc.projects = MagicMock()
    svc.projects.get_active_by_id.return_value = project
    svc.projects.is_member.return_value = is_member
    svc.users = MagicMock()
    svc.users.get_active_by_id.return_value = target
    svc.users.get_by_id.return_value = target
    svc.project_members = MagicMock()
    svc.project_members.get_active_by_project_and_user.return_value = existing
    svc.project_members.add.side_effect = lambda m: m
    return svc, db


def payload(svc, target):
    return ProjectMemberCreate(
        project_id=svc.projects.get_active_by_id.return_value.id, user_id=target.id
    )


def outbox_rows(db):
    return [
        c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], EmailOutbox)
    ]


def test_admin_adds_employee_enqueues_one_email_same_txn():
    caller, target = user(UserRole.admin), user()
    svc, db = make_service(target=target)
    svc.create_project_member(caller, payload(svc, target))
    rows = outbox_rows(db)
    assert len(rows) == 1
    assert rows[0].to_email == target.email
    assert rows[0].organization_id == ORG
    assert "Apollo" in rows[0].subject
    db.commit.assert_not_called()


def test_adding_self_sends_no_email(monkeypatch):
    caller = user(UserRole.admin)
    svc, db = make_service(target=caller)
    monkeypatch.setattr(svc, "_ensure_can_add_member", lambda **k: None)
    svc.create_project_member(caller, payload(svc, caller))
    assert outbox_rows(db) == []


def test_permission_checked_before_duplicate():
    caller, target = user(UserRole.employee), user()
    svc, _ = make_service(target=target, existing=object())
    with pytest.raises(ProjectMemberMutationForbiddenError):
        svc.create_project_member(caller, payload(svc, target))


def test_duplicate_reported_for_permitted_caller():
    caller, target = user(UserRole.admin), user()
    svc, _ = make_service(target=target, existing=object())
    with pytest.raises(ProjectMemberAlreadyExistsError):
        svc.create_project_member(caller, payload(svc, target))


def test_inactive_user_cannot_be_added():
    caller, target = user(UserRole.admin), user(status=UserStatus.invited)
    svc, db = make_service(target=target)
    with pytest.raises(Exception) as exc:
        svc.create_project_member(caller, payload(svc, target))
    assert exc.value.status_code == 409
    assert outbox_rows(db) == []


def test_missing_user_and_foreign_project_rejected():
    caller = user(UserRole.admin)
    svc, _ = make_service(target=None)
    with pytest.raises(UserNotFoundError):
        svc.create_project_member(
            caller, ProjectMemberCreate(project_id=uuid.uuid4(), user_id=uuid.uuid4())
        )
    other_org = SimpleNamespace(id=uuid.uuid4(), name="X", organization_id=uuid.uuid4())
    svc, _ = make_service(project=other_org, target=user())
    with pytest.raises(ProjectNotFoundError):
        svc.create_project_member(
            caller, ProjectMemberCreate(project_id=other_org.id, user_id=uuid.uuid4())
        )


def test_manager_needs_project_membership():
    caller, target = user(UserRole.manager), user()
    svc, _ = make_service(target=target, is_member=False)
    with pytest.raises(ProjectMemberMutationForbiddenError):
        svc.create_project_member(caller, payload(svc, target))


def test_remove_membership_of_deleted_user():
    caller = user(UserRole.admin)
    deleted = user()
    deleted.deleted_at = datetime.now()
    svc, db = make_service(target=deleted)
    member = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=deleted.id,
        project_id=uuid.uuid4(),
        removed_at=None,
        removed_by=None,
    )
    svc.project_members.get_active_by_id.return_value = member
    svc.delete_project_member(member.id, caller)
    assert member.removed_at is not None
    assert member.removed_by == caller.id
    svc.users.get_active_by_id.assert_not_called()


def test_remove_membership_of_missing_user_admin_only():
    member = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        removed_at=None,
        removed_by=None,
    )
    svc, _ = make_service(target=None)
    svc.project_members.get_active_by_id.return_value = member
    svc.delete_project_member(member.id, user(UserRole.admin))
    assert member.removed_at is not None

    member.removed_at = None
    svc, _ = make_service(target=None)
    svc.project_members.get_active_by_id.return_value = member
    with pytest.raises(ProjectMemberMutationForbiddenError):
        svc.delete_project_member(member.id, user(UserRole.employee))


def test_list_scope_by_role():
    svc, _ = make_service()
    page = Pagination(limit=10, offset=5)
    admin, mgr = user(UserRole.admin), user(UserRole.manager)
    svc.list_project_members(caller=admin, pagination=page)
    kw = svc.project_members.list_filtered.call_args.kwargs
    assert kw["visible_to_user_id"] is None and kw["limit"] == 10 and kw["offset"] == 5
    svc.list_project_members(caller=mgr, pagination=page)
    assert (
        svc.project_members.list_filtered.call_args.kwargs["visible_to_user_id"]
        == mgr.id
    )


def test_list_route_paginates(make_client, db):
    client = make_client(UserRole.admin)
    assert client.get("/project-members?limit=0").status_code == 422
    assert client.get("/project-members?limit=5&offset=0").status_code == 200
