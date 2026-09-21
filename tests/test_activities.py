import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.api.pagination import Pagination
from app.core.exception import (
    AppException,
    InsufficientPermissionError,
    NotProjectMemberError,
    ProjectNotFoundError,
    UserNotFoundError,
)
from app.models.enums import UserRole
from app.schemas.activity import ActivityCreate, ActivityUpdate
from app.schemas.activity_assignee import ActivityAssigneeCreate
from app.services.activity import ActivityNotFoundError, ActivityService
from app.services.activity_assignee import ActivityAssigneeService
from tests.conftest import ORG_ID, make_user

PAGE = Pagination(limit=10, offset=0)


def make_activity(**kw):
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        project_id=None,
        name="A",
        description=None,
        status="to_do",
        created_by=uuid.uuid4(),
        updated_by=None,
        created_at=datetime.now(timezone.utc),
        deleted_at=None,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def make_service(activity=None, member=True, assignee=False, project=None):
    svc = ActivityService(MagicMock())
    svc.activities = MagicMock()
    svc.activities.get_active_by_id.return_value = activity
    svc.activities.is_active_assignee.return_value = assignee
    svc.activities.add.side_effect = lambda a: a
    svc.projects = MagicMock()
    svc.projects.is_member.return_value = member
    svc.projects.get_active_by_id.return_value = project
    return svc


# 1. crash regression -------------------------------------------------------


def test_list_activities_does_not_crash_on_status_shadowing(make_client, db):
    client = make_client(UserRole.employee)
    resp = client.get("/activities", params={"status": "to_do"})
    assert resp.status_code == 200
    assert resp.json()["response_data"] == []


def test_list_activities_rejects_bad_status_with_422(make_client):
    assert make_client().get("/activities?status=nope").status_code == 422


def test_route_modules_do_not_shadow_fastapi_status():
    import importlib

    for name in (
        "activities",
        "activity_assignees",
        "time_logs",
        "leave_logs",
        "calendar_events",
        "comments",
        "attachments",
    ):
        module = importlib.import_module(f"app.api.routes.{name}")
        assert module.status.HTTP_200_OK == 200


# 3. activity rules ---------------------------------------------------------


def test_update_schema_rejects_project_id_and_null_required_fields():
    with pytest.raises(ValidationError):
        ActivityUpdate(project_id=str(uuid.uuid4()))
    with pytest.raises(ValidationError):
        ActivityUpdate(name=None)
    with pytest.raises(ValidationError):
        ActivityUpdate(status=None)
    assert ActivityUpdate(description=None).model_dump(exclude_unset=True) == {
        "description": None
    }


def test_create_schema_rejects_blank_name():
    with pytest.raises(ValidationError):
        ActivityCreate(name="   ")
    with pytest.raises(ValidationError):
        ActivityCreate(name="x" * 256)


def test_create_standalone_activity_needs_no_project():
    svc = make_service()
    caller = make_user(UserRole.employee)
    activity = svc.create_activity(ActivityCreate(name="Ops"), caller)
    assert activity.project_id is None and activity.created_by == caller.id


def test_create_rejects_unknown_or_foreign_project():
    caller = make_user(UserRole.admin)
    pid = uuid.uuid4()
    with pytest.raises(ProjectNotFoundError):
        make_service(project=None).create_activity(
            ActivityCreate(name="A", project_id=pid), caller
        )
    foreign = SimpleNamespace(id=pid, organization_id=uuid.uuid4())
    with pytest.raises(ProjectNotFoundError):
        make_service(project=foreign).create_activity(
            ActivityCreate(name="A", project_id=pid), caller
        )


def test_create_requires_membership_except_admin():
    pid = uuid.uuid4()
    project = SimpleNamespace(id=pid, organization_id=ORG_ID)
    payload = ActivityCreate(name="A", project_id=pid)
    for role in (UserRole.employee, UserRole.manager):
        with pytest.raises(NotProjectMemberError):
            make_service(project=project, member=False).create_activity(
                payload, make_user(role)
            )
    make_service(project=project, member=False).create_activity(
        payload, make_user(UserRole.admin)
    )
    make_service(project=project, member=True).create_activity(
        payload, make_user(UserRole.employee)
    )


def test_write_access_matrix():
    other = uuid.uuid4()
    standalone = make_activity(created_by=other)
    in_project = make_activity(created_by=other, project_id=uuid.uuid4())
    admin = make_user(UserRole.admin)
    manager = make_user(UserRole.manager)
    employee = make_user(UserRole.employee)

    svc = make_service()
    assert svc.can_write(admin, standalone)
    assert not svc.can_write(manager, standalone)  # not their standalone
    assert svc.can_write(manager, make_activity(created_by=manager.id))
    assert make_service(member=True).can_write(manager, in_project)
    assert not make_service(member=False).can_write(manager, in_project)
    assert not svc.can_write(employee, standalone)
    assert svc.can_write(employee, make_activity(created_by=employee.id))
    assert make_service(assignee=True).can_write(employee, standalone)


def test_update_and_delete_forbidden_without_write_access():
    activity = make_activity(created_by=uuid.uuid4())
    svc = make_service(activity=activity)
    employee = make_user(UserRole.employee)
    with pytest.raises(InsufficientPermissionError):
        svc.update_activity(activity.id, ActivityUpdate(name="B"), employee)
    with pytest.raises(InsufficientPermissionError):
        svc.delete_activity(activity.id, employee)


def test_update_other_org_activity_is_404():
    activity = make_activity(organization_id=uuid.uuid4())
    svc = make_service(activity=activity)
    with pytest.raises(ActivityNotFoundError):
        svc.update_activity(
            activity.id, ActivityUpdate(name="B"), make_user(UserRole.admin)
        )


def test_update_sets_updated_by_and_never_commits():
    caller = make_user(UserRole.admin)
    activity = make_activity()
    svc = make_service(activity=activity)
    svc.update_activity(activity.id, ActivityUpdate(name="New"), caller)
    assert activity.name == "New" and activity.updated_by == caller.id
    svc.db.commit.assert_not_called()


def test_list_passes_pagination_and_status_filter():
    svc = make_service()
    svc.list_activities(PAGE, status_filter="done")
    kwargs = svc.activities.list_filtered.call_args.kwargs
    assert kwargs["limit"] == 10 and kwargs["status"] == "done"


def test_create_activity_route_commits_once(make_client, db):
    client = make_client(UserRole.employee)

    def fill_defaults(obj):
        obj.id = uuid.uuid4()
        obj.status = "to_do"
        obj.created_at = datetime.now(timezone.utc)
        obj.updated_by = None

    db.refresh.side_effect = fill_defaults
    resp = client.post("/activities", json={"name": "Ops"})
    assert resp.status_code == 201, resp.text
    db.commit.assert_called_once()


# 4. assignees --------------------------------------------------------------


def make_assignee_service(activity, user, member=True, existing=None):
    svc = ActivityAssigneeService(MagicMock())
    svc.activities = MagicMock()
    svc.activities.get_visible_activity.return_value = activity
    svc.activities.can_write.return_value = True
    svc.users = MagicMock()
    svc.users.get_active_by_id.return_value = user
    svc.projects = MagicMock()
    svc.projects.is_member.return_value = member
    svc.assignees = MagicMock()
    svc.assignees.get_active_assignee.return_value = existing
    svc.assignees.add.side_effect = lambda a: a
    return svc


def assignee_payload(activity, user):
    return ActivityAssigneeCreate(activity_id=activity.id, user_id=user.id)


def test_assign_requires_manager_role():
    activity = make_activity()
    user = make_user(UserRole.employee)
    svc = make_assignee_service(activity, user)
    with pytest.raises(InsufficientPermissionError):
        svc.create_assignee(
            assignee_payload(activity, user), make_user(UserRole.employee)
        )


def test_assign_manager_needs_write_access_to_activity():
    activity = make_activity()
    user = make_user(UserRole.employee)
    svc = make_assignee_service(activity, user)
    svc.activities.can_write.return_value = False
    with pytest.raises(InsufficientPermissionError):
        svc.create_assignee(assignee_payload(activity, user), make_user(UserRole.manager))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda u: setattr(u, "status", "suspended"),
        lambda u: setattr(u, "organization_id", uuid.uuid4()),
    ],
)
def test_assign_rejects_inactive_or_foreign_user(mutate):
    activity = make_activity()
    user = make_user(UserRole.employee)
    mutate(user)
    svc = make_assignee_service(activity, user)
    with pytest.raises(UserNotFoundError):
        svc.create_assignee(assignee_payload(activity, user), make_user(UserRole.admin))


def test_assign_rejects_missing_user():
    activity = make_activity()
    svc = make_assignee_service(activity, None)
    with pytest.raises(UserNotFoundError):
        svc.create_assignee(
            ActivityAssigneeCreate(activity_id=activity.id, user_id=uuid.uuid4()),
            make_user(UserRole.admin),
        )


def test_assign_requires_project_membership_of_assignee():
    activity = make_activity(project_id=uuid.uuid4())
    user = make_user(UserRole.employee)
    svc = make_assignee_service(activity, user, member=False)
    with pytest.raises(AppException) as exc:
        svc.create_assignee(assignee_payload(activity, user), make_user(UserRole.admin))
    assert exc.value.status_code == 422


def test_assign_duplicate_is_409_and_success_never_commits():
    activity = make_activity()
    user = make_user(UserRole.employee)
    admin = make_user(UserRole.admin)
    svc = make_assignee_service(activity, user, existing=object())
    with pytest.raises(AppException) as exc:
        svc.create_assignee(assignee_payload(activity, user), admin)
    assert exc.value.status_code == 409

    svc = make_assignee_service(activity, user)
    assignee = svc.create_assignee(assignee_payload(activity, user), admin)
    assert assignee.assigned_by == admin.id and assignee.user_id == user.id
    svc.db.commit.assert_not_called()


def test_unassign_requires_write_access():
    activity = make_activity()
    svc = make_assignee_service(activity, None)
    svc.assignees.get_active_assignee_by_id.return_value = SimpleNamespace(
        id=uuid.uuid4(), activity_id=activity.id
    )
    svc.activities.can_write.return_value = False
    with pytest.raises(InsufficientPermissionError):
        svc.delete_assignee(uuid.uuid4(), make_user(UserRole.manager))
    svc.activities.can_write.return_value = True
    svc.delete_assignee(uuid.uuid4(), make_user(UserRole.manager))
    svc.assignees.soft_delete.assert_called_once()


def test_assignee_routes_forbid_employees(make_client):
    client = make_client(UserRole.employee)
    resp = client.post(
        "/activity-assignees",
        json={"activity_id": str(uuid.uuid4()), "user_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 403
    assert make_client(UserRole.admin).get("/activity-assignees").status_code == 200
