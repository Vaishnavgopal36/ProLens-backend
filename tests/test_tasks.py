import datetime as dt
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.exception import (
    AppException,
    CrossOrganizationForbiddenError,
    EmployeeOnLeaveError,
    FeatureNotFoundError,
    InsufficientPermissionError,
    NotProjectMemberError,
    ProjectMembershipRequiredError,
    TaskNotFoundError,
    UserNotFoundError,
)
from app.models.enums import UserRole
from app.repositories.task_assignee_repository import TaskAssigneeRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.task import TaskCreate, TaskUpdate
from app.schemas.task_assignee import TaskAssigneeCreate
from app.services.task_assignee import TaskAssigneeService
from app.services.task_service import TaskService
from tests.conftest import ORG_ID, make_user

PROJECT_ID = uuid.uuid4()
FEATURE_ID = uuid.uuid4()


def feature(project_id=PROJECT_ID, org=ORG_ID, deleted=False):
    return SimpleNamespace(
        id=FEATURE_ID,
        project_id=project_id,
        organization_id=org,
        deleted_at=object() if deleted else None,
    )


def task(feature_id=FEATURE_ID, created_by=None, **kw):
    return SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        feature_id=feature_id,
        created_by=created_by or uuid.uuid4(),
        start_date=None,
        due_date=None,
        deleted_at=None,
        **kw,
    )


def make_service(task_obj=None, feat=None, member=True, assignee=False):
    svc = TaskService(MagicMock())
    svc.tasks = MagicMock()
    svc.tasks.get_active_by_id.return_value = task_obj
    svc.tasks.add.side_effect = lambda t: t
    svc.features = MagicMock()
    svc.features.get_by_id.return_value = feat
    svc.features.get_active_by_id.return_value = (
        feat if feat and not feat.deleted_at else None
    )
    svc.projects = MagicMock()
    svc.projects.is_member.return_value = member
    svc.projects.get_active_by_id.return_value = SimpleNamespace(id=PROJECT_ID)
    svc.task_assignees = MagicMock()
    svc.task_assignees.is_active_assignee.return_value = assignee
    return svc


# ---- 1. crash regression: manager create/update/delete ----


def test_manager_task_lifecycle_does_not_crash():
    manager = make_user(UserRole.manager)
    t = task()
    svc = make_service(t, feature())
    assert not hasattr(svc, "project_members")

    created = svc.create_task(manager, TaskCreate(feature_id=FEATURE_ID, name="x"))
    assert created.feature_id == FEATURE_ID
    svc.update_task(manager, t.id, TaskUpdate(name="y"))
    svc.delete_task(manager, t.id)
    assert t.deleted_at is not None and t.deleted_by == manager.id
    svc.projects.is_member.assert_called_with(PROJECT_ID, manager.id)


# ---- 6. access control ----


def test_manager_non_member_cannot_write():
    manager = make_user(UserRole.manager)
    t = task()
    svc = make_service(t, feature(), member=False)
    with pytest.raises(InsufficientPermissionError):
        svc.update_task(manager, t.id, TaskUpdate(name="y"))
    with pytest.raises(InsufficientPermissionError):
        svc.delete_task(manager, t.id)
    with pytest.raises(NotProjectMemberError):
        svc.create_task(manager, TaskCreate(feature_id=FEATURE_ID, name="x"))


def test_manager_standalone_task_only_creator():
    manager = make_user(UserRole.manager)
    svc = make_service(task(feature_id=None), None)
    other = svc.tasks.get_active_by_id.return_value
    with pytest.raises(InsufficientPermissionError):
        svc.update_task(manager, other.id, TaskUpdate(name="y"))
    other.created_by = manager.id
    svc.update_task(manager, other.id, TaskUpdate(name="y"))


def test_admin_can_write_anything():
    admin = make_user(UserRole.admin)
    t = task()
    svc = make_service(t, feature(), member=False)
    svc.update_task(admin, t.id, TaskUpdate(name="y"))
    svc.delete_task(admin, t.id)


def test_employee_create_rules():
    emp = make_user(UserRole.employee)
    svc = make_service(None, feature(), member=False)
    assert svc.create_task(emp, TaskCreate(name="personal")).feature_id is None
    with pytest.raises(NotProjectMemberError):
        svc.create_task(emp, TaskCreate(feature_id=FEATURE_ID, name="x"))
    svc.projects.is_member.return_value = True
    assert svc.create_task(emp, TaskCreate(feature_id=FEATURE_ID, name="x"))


def test_employee_update_delete_only_when_assignee_or_creator():
    emp = make_user(UserRole.employee)
    t = task()
    svc = make_service(t, feature(), assignee=False)
    with pytest.raises(InsufficientPermissionError):
        svc.update_task(emp, t.id, TaskUpdate(name="y"))
    with pytest.raises(InsufficientPermissionError):
        svc.delete_task(emp, t.id)

    t.created_by = emp.id  # creator may delete, but not update
    svc.delete_task(emp, t.id)
    t.deleted_at = None
    with pytest.raises(InsufficientPermissionError):
        svc.update_task(emp, t.id, TaskUpdate(name="y"))

    svc.task_assignees.is_active_assignee.return_value = True
    svc.update_task(emp, t.id, TaskUpdate(name="y"))


def test_employee_cannot_change_feature_id():
    emp = make_user(UserRole.employee)
    t = task()
    svc = make_service(t, feature(), assignee=True)
    with pytest.raises(InsufficientPermissionError):
        svc.update_task(emp, t.id, TaskUpdate(feature_id=uuid.uuid4()))
    with pytest.raises(InsufficientPermissionError):
        svc.update_task(emp, t.id, TaskUpdate(feature_id=None))
    # same value is not a move
    svc.update_task(emp, t.id, TaskUpdate(feature_id=FEATURE_ID, name="z"))


def test_manager_move_needs_both_projects_and_valid_target():
    manager = make_user(UserRole.manager)
    t = task()
    target = uuid.uuid4()
    svc = make_service(t, feature())
    other_project = uuid.uuid4()
    target_feature = feature(project_id=other_project)
    target_feature.id = target
    svc.features.get_active_by_id.return_value = target_feature

    svc.projects.is_member.side_effect = lambda pid, uid: pid == PROJECT_ID
    with pytest.raises(NotProjectMemberError):
        svc.update_task(manager, t.id, TaskUpdate(feature_id=target))

    svc.projects.is_member.side_effect = lambda pid, uid: True
    svc.update_task(manager, t.id, TaskUpdate(feature_id=target))
    assert t.feature_id == target

    # source not writable
    svc.projects.is_member.side_effect = lambda pid, uid: pid == other_project
    with pytest.raises(InsufficientPermissionError):
        svc.update_task(manager, t.id, TaskUpdate(feature_id=FEATURE_ID))


@pytest.mark.parametrize("bad", ["missing", "deleted", "other_org"])
def test_move_and_create_reject_bad_feature(bad):
    admin = make_user(UserRole.admin)
    t = task()
    svc = make_service(t, feature())
    if bad == "missing":
        svc.features.get_active_by_id.return_value = None
    elif bad == "deleted":
        svc.features.get_active_by_id.return_value = None  # repo hides soft-deleted
    else:
        svc.features.get_active_by_id.return_value = feature(org=uuid.uuid4())
    with pytest.raises(FeatureNotFoundError):
        svc.create_task(admin, TaskCreate(feature_id=uuid.uuid4(), name="x"))
    with pytest.raises(FeatureNotFoundError):
        svc.update_task(admin, t.id, TaskUpdate(feature_id=uuid.uuid4()))


def test_update_missing_task_404_and_date_ordering():
    admin = make_user(UserRole.admin)
    svc = make_service(None, None)
    with pytest.raises(TaskNotFoundError):
        svc.update_task(admin, uuid.uuid4(), TaskUpdate(name="x"))
    t = task()
    t.due_date = dt.date(2026, 1, 1)
    svc = make_service(t, feature())
    with pytest.raises(AppException) as e:
        svc.update_task(admin, t.id, TaskUpdate(start_date=dt.date(2026, 2, 1)))
    assert e.value.status_code == 422


# ---- visibility scoping (SQL shape) ----


def _sql(caller):
    db = MagicMock()
    TaskRepository(db).list_filtered(caller=caller)
    stmt = db.scalars.call_args[0][0]
    return str(stmt.compile(compile_kwargs={"literal_binds": False}))


def test_list_scoping_and_pagination_in_sql():
    admin_sql = _sql(make_user(UserRole.admin))
    emp_sql = _sql(make_user(UserRole.employee))
    assert "project_members" not in admin_sql
    assert "project_members" in emp_sql and "task_assignees" in emp_sql
    assert "ORDER BY tasks.created_at, tasks.id" in emp_sql
    assert "LIMIT" in emp_sql and "OFFSET" in emp_sql


# ---- 7. schema validation ----


def test_task_schema_validation():
    with pytest.raises(ValidationError):
        TaskCreate(name="")
    with pytest.raises(ValidationError):
        TaskCreate(name="x" * 256)
    with pytest.raises(ValidationError):
        TaskCreate(name="x", description="d" * 10_001)
    with pytest.raises(ValidationError):
        TaskCreate(
            name="x", start_date=dt.date(2026, 2, 1), due_date=dt.date(2026, 1, 1)
        )
    TaskCreate(name="x", start_date=dt.date(2026, 1, 1), due_date=dt.date(2026, 1, 1))
    for field in ("name", "status", "priority"):
        with pytest.raises(ValidationError):
            TaskUpdate(**{field: None})
    assert TaskUpdate(description=None, feature_id=None).model_dump(exclude_unset=True)
    assert "created_by" not in TaskUpdate.model_fields


def test_task_update_null_is_422_over_http(make_client):
    client = make_client(UserRole.admin)
    r = client.patch(f"/tasks/{uuid.uuid4()}", json={"name": None})
    assert r.status_code == 422
    assert client.get("/tasks?limit=0").status_code == 422


def test_task_list_ok_over_http(make_client):
    client = make_client(UserRole.employee)
    assert client.get("/tasks?limit=5&offset=0").status_code == 200


# ---- 3/4. assignee service ----


def assignee_service(t, user, feat=None, member=True, existing=None, leave=None):
    svc = TaskAssigneeService(MagicMock())
    svc.tasks = MagicMock()
    svc.tasks.get_active_by_id.return_value = t
    svc.users = MagicMock()
    svc.users.get_active_by_id.return_value = user
    svc.features = MagicMock()
    svc.features.get_by_id.return_value = feat
    svc.projects = MagicMock()
    svc.projects.is_member.return_value = member
    svc.assignees = MagicMock()
    svc.assignees.get_active_by_task_and_user.return_value = existing
    svc.assignees.get_conflicting_leave.return_value = leave
    svc.assignees.add.side_effect = lambda a: a
    svc.task_service = make_service(t, feat, member=member)
    return svc


def target_user(**kw):
    u = make_user(UserRole.employee)
    u.status = kw.get("status", "active")
    u.organization_id = kw.get("org", ORG_ID)
    return u


def payload(t, u):
    return TaskAssigneeCreate(task_id=t.id, user_id=u.id)


def test_assignee_create_happy_path_and_no_commit():
    admin = make_user(UserRole.admin)
    t, u = task(), target_user()
    from app.models.enums import UserStatus

    u.status = UserStatus.active
    svc = assignee_service(t, u, feature())
    a = svc.create_assignee(payload(t, u), admin)
    assert a.user_id == u.id and a.assigned_by == admin.id
    svc.db.commit.assert_not_called()


def _active(u):
    from app.models.enums import UserStatus

    u.status = UserStatus.active
    return u


def test_assignee_user_validation():
    admin = make_user(UserRole.admin)
    t = task()
    with pytest.raises(UserNotFoundError):
        assignee_service(t, None).create_assignee(
            TaskAssigneeCreate(task_id=t.id, user_id=uuid.uuid4()), admin
        )
    inactive = (
        target_user()
    )  # status "active" str != UserStatus.active? enum is str subclass
    from app.models.enums import UserStatus

    inactive.status = UserStatus.suspended
    with pytest.raises(UserNotFoundError):
        assignee_service(t, inactive, feature()).create_assignee(
            payload(t, inactive), admin
        )
    foreign = _active(target_user(org=uuid.uuid4()))
    with pytest.raises(CrossOrganizationForbiddenError):
        assignee_service(t, foreign, feature()).create_assignee(
            payload(t, foreign), admin
        )


def test_assignee_duplicate_is_409():
    admin = make_user(UserRole.admin)
    t, u = task(), _active(target_user())
    svc = assignee_service(t, u, feature(), existing=object())
    with pytest.raises(AppException) as e:
        svc.create_assignee(payload(t, u), admin)
    assert e.value.status_code == 409


def test_assignee_integrity_error_race_is_409():
    from sqlalchemy.exc import IntegrityError

    admin = make_user(UserRole.admin)
    t, u = task(), _active(target_user())
    svc = assignee_service(t, u, feature())
    svc.assignees.add.side_effect = IntegrityError("x", {}, Exception())
    with pytest.raises(AppException) as e:
        svc.create_assignee(payload(t, u), admin)
    assert e.value.status_code == 409


def test_assignee_must_be_project_member_only_for_feature_tasks():
    admin = make_user(UserRole.admin)
    t, u = task(), _active(target_user())
    svc = assignee_service(t, u, feature(), member=False)
    with pytest.raises(ProjectMembershipRequiredError):
        svc.create_assignee(payload(t, u), admin)

    standalone = task(feature_id=None)
    svc = assignee_service(standalone, u, None, member=False)
    assert svc.create_assignee(payload(standalone, u), admin)


def test_assignee_authorization():
    t, u = task(), _active(target_user())
    for role in (UserRole.employee,):
        with pytest.raises(InsufficientPermissionError):
            assignee_service(t, u, feature()).create_assignee(
                payload(t, u), make_user(role)
            )
    manager = make_user(UserRole.manager)
    with pytest.raises(InsufficientPermissionError):
        assignee_service(t, u, feature(), member=False).create_assignee(
            payload(t, u), manager
        )
    with pytest.raises(TaskNotFoundError):
        assignee_service(None, u).create_assignee(
            TaskAssigneeCreate(task_id=uuid.uuid4(), user_id=u.id), manager
        )


def test_assignee_leave_conflict_raises():
    admin = make_user(UserRole.admin)
    t, u = task(), _active(target_user())
    t.start_date, t.due_date = dt.date(2026, 5, 1), dt.date(2026, 5, 5)
    svc = assignee_service(t, u, feature(), leave=object())
    with pytest.raises(EmployeeOnLeaveError):
        svc.create_assignee(payload(t, u), admin)
    svc.assignees.get_conflicting_leave.assert_called_with(
        u.id, t.start_date, t.due_date
    )


def test_assignee_delete_authorization_and_no_commit():
    manager = make_user(UserRole.manager)
    t, u = task(), _active(target_user())
    svc = assignee_service(t, u, feature())
    a = SimpleNamespace(task_id=t.id, removed_at=None, removed_by=None)
    svc.assignees.get_active_by_id.return_value = a
    svc.tasks.get_by_id.return_value = t
    svc.delete_assignee(uuid.uuid4(), manager)
    assert a.removed_at is not None and a.removed_by == manager.id
    svc.db.commit.assert_not_called()

    svc.task_service.projects.is_member.return_value = False
    with pytest.raises(InsufficientPermissionError):
        svc.delete_assignee(uuid.uuid4(), manager)
    svc.assignees.get_active_by_id.return_value = None
    with pytest.raises(AppException) as e:
        svc.delete_assignee(uuid.uuid4(), manager)
    assert e.value.status_code == 404


def test_single_task_assignee_repository():
    import importlib.util

    assert importlib.util.find_spec("app.repositories.task_assignee") is None


# ---- 5. leave overlap boundaries (real SQL on sqlite) ----

USER = uuid.uuid4()


@pytest.fixture
def leave_repo():
    engine = create_engine("sqlite://")
    with engine.begin() as c:
        c.execute(
            text(
                "create table leave_logs (id char(32), organization_id char(32), "
                "user_id char(32), start_date date, end_date date, leave_type varchar, "
                "reason text, deleted_at datetime, deleted_by char(32), "
                "created_at datetime, updated_at datetime)"
            )
        )
    with Session(engine) as s:

        def add(start, end, user=USER, deleted=False):
            s.execute(
                text(
                    "insert into leave_logs (id, user_id, start_date, end_date, deleted_at) "
                    "values (:i, :u, :s, :e, :d)"
                ),
                {
                    "i": uuid.uuid4().hex,
                    "u": user.hex,
                    "s": start,
                    "e": end,
                    "d": "2026-01-01 00:00:00" if deleted else None,
                },
            )

        repo = TaskAssigneeRepository(s)
        repo.add_leave = add
        yield repo


D = dt.date


@pytest.mark.parametrize(
    "window,expected",
    [
        ((D(2026, 5, 1), D(2026, 5, 9)), False),  # ends the day before leave
        ((D(2026, 5, 1), D(2026, 5, 10)), True),  # touches first leave day
        ((D(2026, 5, 11), D(2026, 5, 11)), True),  # inside
        ((D(2026, 5, 12), D(2026, 5, 20)), True),  # touches last leave day
        ((D(2026, 5, 13), D(2026, 5, 20)), False),  # starts the day after leave
        ((D(2026, 5, 1), D(2026, 5, 31)), True),  # engulfs leave
        ((None, D(2026, 5, 11)), True),  # only due date
        ((D(2026, 5, 11), None), True),  # only start date
        ((None, D(2026, 5, 13)), False),
        ((None, None), False),  # no dates => no conflict
    ],
)
def test_leave_overlap_boundaries(leave_repo, window, expected):
    leave_repo.add_leave("2026-05-10", "2026-05-12")
    result = leave_repo.get_conflicting_leave(USER, *window)
    assert (result is not None) is expected


def test_leave_ignores_deleted_and_other_users(leave_repo):
    leave_repo.add_leave("2026-05-10", "2026-05-12", deleted=True)
    leave_repo.add_leave("2026-05-10", "2026-05-12", user=uuid.uuid4())
    assert (
        leave_repo.get_conflicting_leave(USER, D(2026, 5, 11), D(2026, 5, 11)) is None
    )
