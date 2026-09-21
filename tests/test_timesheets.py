import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.api.pagination import Pagination
from app.core.exception import InsufficientPermissionError, TaskNotFoundError
from app.models.enums import UserRole
from app.schemas.time_log import TimeLogCreate, TimeLogUpdate
from app.services.activity import ActivityNotFoundError
from app.services.time_log import TimeLogNotFoundError, TimeLogService
from tests.conftest import ORG_ID, make_user

PAGE = Pagination(limit=50, offset=0)
TODAY = date(2026, 1, 1)


def make_service(task=None, activity=None, assigned=True):
    svc = TimeLogService(MagicMock())
    svc.time_logs = MagicMock()
    svc.time_logs.get_task.return_value = task
    svc.time_logs.get_activity.return_value = activity
    svc.time_logs.is_task_assignee.return_value = assigned
    svc.time_logs.is_activity_assignee.return_value = assigned
    svc.time_logs.add.side_effect = lambda t: t
    return svc


def target(**kw):
    fields = dict(id=uuid.uuid4(), organization_id=ORG_ID, deleted_at=None)
    fields.update(kw)
    return SimpleNamespace(**fields)


# schema --------------------------------------------------------------------


@pytest.mark.parametrize("minutes", [0, -5, 1441])
def test_duration_bounds_enforced(minutes):
    with pytest.raises(ValidationError):
        TimeLogCreate(task_id=uuid.uuid4(), log_date=TODAY, duration_minutes=minutes)
    with pytest.raises(ValidationError):
        TimeLogUpdate(duration_minutes=minutes)


def test_exactly_one_target_uses_is_not_none():
    kw = dict(log_date=TODAY, duration_minutes=60)
    with pytest.raises(ValidationError):
        TimeLogCreate(**kw)
    with pytest.raises(ValidationError):
        TimeLogCreate(task_id=uuid.uuid4(), activity_id=uuid.uuid4(), **kw)
    assert TimeLogCreate(activity_id=uuid.uuid4(), **kw).task_id is None


def test_update_cannot_change_target_or_null_required_fields():
    with pytest.raises(ValidationError):
        TimeLogUpdate(task_id=str(uuid.uuid4()))
    with pytest.raises(ValidationError):
        TimeLogUpdate(activity_id=str(uuid.uuid4()))
    with pytest.raises(ValidationError):
        TimeLogUpdate(log_date=None)
    with pytest.raises(ValidationError):
        TimeLogUpdate(duration_minutes=None)
    assert TimeLogUpdate(description=None).model_dump(exclude_unset=True) == {
        "description": None
    }


def test_patch_route_rejects_task_id_with_422(make_client):
    resp = make_client().patch(
        f"/time-logs/{uuid.uuid4()}", json={"task_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 422


# create rules --------------------------------------------------------------


def create_payload(**kw):
    return TimeLogCreate(log_date=TODAY, duration_minutes=30, **kw)


def test_create_requires_existing_same_org_task():
    caller = make_user(UserRole.employee)
    payload = create_payload(task_id=uuid.uuid4())
    with pytest.raises(TaskNotFoundError):
        make_service(task=None).create_time_log(payload, caller)
    with pytest.raises(TaskNotFoundError):
        make_service(task=target(organization_id=uuid.uuid4())).create_time_log(
            payload, caller
        )
    deleted = target()
    deleted.deleted_at = datetime.now(timezone.utc)
    with pytest.raises(TaskNotFoundError):
        make_service(task=deleted).create_time_log(payload, caller)


def test_create_requires_existing_activity():
    with pytest.raises(ActivityNotFoundError):
        make_service(activity=None).create_time_log(
            create_payload(activity_id=uuid.uuid4()), make_user()
        )


def test_create_requires_assignment_except_admin():
    task = target()
    payload = create_payload(task_id=task.id)
    with pytest.raises(InsufficientPermissionError):
        make_service(task=task, assigned=False).create_time_log(
            payload, make_user(UserRole.employee)
        )
    with pytest.raises(InsufficientPermissionError):
        make_service(task=task, assigned=False).create_time_log(
            payload, make_user(UserRole.manager)
        )
    admin = make_user(UserRole.admin)
    log = make_service(task=task, assigned=False).create_time_log(payload, admin)
    assert log.user_id == admin.id

    activity = target()
    with pytest.raises(InsufficientPermissionError):
        make_service(activity=activity, assigned=False).create_time_log(
            create_payload(activity_id=activity.id), make_user()
        )


def test_create_assigned_employee_succeeds_without_commit():
    task = target()
    caller = make_user(UserRole.employee)
    svc = make_service(task=task, assigned=True)
    log = svc.create_time_log(create_payload(task_id=task.id), caller)
    assert log.task_id == task.id and log.activity_id is None
    svc.db.commit.assert_not_called()


# visibility ----------------------------------------------------------------


def test_employee_only_lists_own_logs():
    caller = make_user(UserRole.employee)
    svc = make_service()
    svc.list_time_logs(caller, PAGE)
    assert svc.time_logs.list_filtered.call_args.kwargs["user_id"] == caller.id
    svc.list_time_logs(caller, PAGE, user_id=caller.id)
    with pytest.raises(InsufficientPermissionError):
        svc.list_time_logs(caller, PAGE, user_id=uuid.uuid4())


@pytest.mark.parametrize("role", [UserRole.manager, UserRole.admin])
def test_managers_and_admins_list_anyones_logs(role):
    svc = make_service()
    other = uuid.uuid4()
    svc.list_time_logs(make_user(role), PAGE, user_id=other)
    assert svc.time_logs.list_filtered.call_args.kwargs["user_id"] == other
    svc.list_time_logs(make_user(role), PAGE)
    assert svc.time_logs.list_filtered.call_args.kwargs["user_id"] is None


def test_list_route_denies_employee_foreign_user_filter(make_client):
    resp = make_client(UserRole.employee).get(f"/time-logs?user_id={uuid.uuid4()}")
    assert resp.status_code == 403
    assert make_client(UserRole.employee).get("/time-logs").status_code == 200


# update / delete -----------------------------------------------------------


def test_update_and_delete_owner_only_and_no_commit():
    owner = make_user(UserRole.employee)
    log = SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        user_id=owner.id,
        duration_minutes=10,
        deleted_at=None,
    )
    svc = make_service()
    svc.time_logs.get_active_by_id.return_value = log

    svc.update_time_log(log.id, TimeLogUpdate(duration_minutes=90), owner)
    assert log.duration_minutes == 90
    svc.delete_time_log(log.id, owner)
    svc.db.commit.assert_not_called()

    with pytest.raises(InsufficientPermissionError):
        svc.update_time_log(
            log.id, TimeLogUpdate(duration_minutes=5), make_user(UserRole.admin)
        )
    with pytest.raises(InsufficientPermissionError):
        svc.delete_time_log(log.id, make_user(UserRole.manager))

    svc.time_logs.get_active_by_id.return_value = None
    with pytest.raises(TimeLogNotFoundError):
        svc.delete_time_log(log.id, owner)
