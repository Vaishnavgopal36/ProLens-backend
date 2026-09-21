import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import DataError, IntegrityError

from app.api.pagination import Pagination
from app.core.exception import AppException, InsufficientPermissionError
from app.models.enums import CalendarEventType, LeaveType, UserRole
from app.models.timesheet import CalendarEvent, LeaveLog
from app.schemas.calendar_event import CalendarEventCreate, CalendarEventUpdate
from app.schemas.leave_log import LeaveLogCreate, LeaveLogUpdate
from app.services.calendar_event_service import CalendarEventService
from app.services.leave_log_service import LeaveLogService
from tests.conftest import ORG_ID, make_user

PAGE = Pagination(limit=50, offset=0)
UTC = timezone.utc
T0 = datetime(2026, 3, 1, 9, tzinfo=UTC)
T1 = T0 + timedelta(hours=2)


def today() -> date:
    return datetime.now(UTC).date()


# ---- leave schema ---------------------------------------------------------


def test_leave_schema_validation():
    d = today()
    with pytest.raises(ValidationError):
        LeaveLogCreate(
            start_date=d + timedelta(days=2),
            end_date=d,
            leave_type=LeaveType.sick,
        )
    with pytest.raises(ValidationError):
        LeaveLogCreate(
            start_date=d, end_date=d, leave_type=LeaveType.sick, reason="x" * 2001
        )
    with pytest.raises(ValidationError):
        LeaveLogUpdate(reason="x" * 2001)
    with pytest.raises(ValidationError):
        LeaveLogUpdate(start_date=None)
    with pytest.raises(ValidationError):
        LeaveLogUpdate(leave_type=None)
    with pytest.raises(ValidationError):
        LeaveLogUpdate(start_date=d + timedelta(days=3), end_date=d)
    assert LeaveLogUpdate(reason=None).reason is None


# ---- leave service --------------------------------------------------------


def make_leave(user_id, start, end, reason="private"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        user_id=user_id,
        start_date=start,
        end_date=end,
        leave_type=LeaveType.casual,
        reason=reason,
        created_at=datetime.now(UTC),
        deleted_at=None,
    )


def make_leave_service(leave=None, event=None):
    svc = LeaveLogService(MagicMock())
    svc.leave_logs = MagicMock()
    svc.leave_logs.get_active_by_id.return_value = leave
    svc.events = MagicMock()
    svc.events.get_active_by_source_leave_log.return_value = event
    svc.users = MagicMock()
    svc.users.get_by_id.return_value = SimpleNamespace(
        first_name="Ada", last_name="Lovelace", email="a@x.io"
    )
    return svc


def integrity_error(pgcode=None, constraint=None):
    orig = SimpleNamespace(
        pgcode=pgcode, diag=SimpleNamespace(constraint_name=constraint)
    )
    return IntegrityError("stmt", {}, orig)


def test_overlap_exclusion_violation_is_409():
    svc = make_leave_service()
    svc.db.flush.side_effect = integrity_error("23P01", "excl_leave_logs_no_overlap")
    d = today()
    payload = LeaveLogCreate(start_date=d, end_date=d, leave_type=LeaveType.sick)
    with pytest.raises(AppException) as exc:
        svc.create_leave_log(payload, make_user())
    assert exc.value.status_code == 409
    assert "Overlapping" in exc.value.message


def test_other_integrity_error_is_not_reported_as_overlap():
    svc = make_leave_service()
    svc.db.flush.side_effect = integrity_error("23503", "leave_logs_user_id_fkey")
    d = today()
    payload = LeaveLogCreate(start_date=d, end_date=d, leave_type=LeaveType.sick)
    with pytest.raises(AppException) as exc:
        svc.create_leave_log(payload, make_user())
    assert exc.value.status_code == 400
    assert "Overlapping" not in exc.value.message


def test_data_error_is_422():
    svc = make_leave_service()
    svc.db.flush.side_effect = DataError("stmt", {}, Exception("out of range"))
    d = today()
    payload = LeaveLogCreate(start_date=d, end_date=d, leave_type=LeaveType.sick)
    with pytest.raises(AppException) as exc:
        svc.create_leave_log(payload, make_user())
    assert exc.value.status_code == 422


def test_create_leave_creates_system_calendar_event():
    svc = make_leave_service()

    def fake_add(obj):  # emulate flush assigning the PK / server defaults
        obj.id = uuid.uuid4()
        obj.created_at = datetime.now(UTC)

    svc.db.add.side_effect = fake_add
    caller = make_user(UserRole.employee, first_name="x")
    d = today() + timedelta(days=5)
    payload = LeaveLogCreate(
        start_date=d, end_date=d + timedelta(days=1), leave_type=LeaveType.casual
    )
    result = svc.create_leave_log(payload, caller)

    (leave,) = [
        c.args[0] for c in svc.db.add.call_args_list if isinstance(c.args[0], LeaveLog)
    ]
    event = svc.events.add.call_args.args[0]
    assert isinstance(event, CalendarEvent)
    assert event.event_type == CalendarEventType.leave
    assert event.source_leave_log_id == leave.id
    assert event.title == "Ada Lovelace on leave"
    assert event.created_by == caller.id
    assert event.start_time == datetime.combine(d, datetime.min.time(), tzinfo=UTC)
    assert (event.end_time.hour, event.end_time.minute, event.end_time.second) == (
        23,
        59,
        59,
    )
    assert result.user_id == caller.id
    svc.db.commit.assert_not_called()


def test_update_leave_updates_event_and_delete_soft_deletes_it():
    owner = make_user(UserRole.employee)
    d = today() + timedelta(days=10)
    leave = make_leave(owner.id, d, d)
    event = SimpleNamespace(start_time=None, end_time=None)
    svc = make_leave_service(leave, event)
    new_end = d + timedelta(days=2)
    svc.update_leave_log(leave.id, LeaveLogUpdate(end_date=new_end), owner)
    assert event.end_time.date() == new_end
    assert event.start_time.date() == d

    svc.delete_leave_log(leave.id, owner)
    svc.leave_logs.soft_delete.assert_called_once()
    svc.events.soft_delete.assert_called_once_with(event, deleted_by=owner.id)


def test_employee_cannot_move_leave_into_past_utc():
    owner = make_user(UserRole.employee)
    d = today() + timedelta(days=10)
    leave = make_leave(owner.id, d, d + timedelta(days=1))
    svc = make_leave_service(leave)
    with pytest.raises(AppException) as exc:
        svc.update_leave_log(
            leave.id,
            LeaveLogUpdate(start_date=today() - timedelta(days=1), end_date=d),
            owner,
        )
    assert exc.value.status_code == 422


def test_update_validates_merged_dates():
    owner = make_user(UserRole.employee)
    d = today() + timedelta(days=10)
    leave = make_leave(owner.id, d, d + timedelta(days=1))
    svc = make_leave_service(leave)
    with pytest.raises(AppException) as exc:
        svc.update_leave_log(
            leave.id, LeaveLogUpdate(start_date=d + timedelta(days=5)), owner
        )
    assert exc.value.status_code == 422


def test_leave_write_permissions():
    owner = make_user(UserRole.employee)
    d = today() + timedelta(days=10)
    future = make_leave(owner.id, d, d)
    started = make_leave(owner.id, today(), today())
    payload = LeaveLogUpdate(reason="x")

    svc = make_leave_service(future)
    with pytest.raises(InsufficientPermissionError):
        svc.update_leave_log(future.id, payload, make_user(UserRole.employee))
    with pytest.raises(InsufficientPermissionError):
        svc.delete_leave_log(future.id, make_user(UserRole.manager))
    svc.update_leave_log(future.id, payload, make_user(UserRole.manager))

    svc = make_leave_service(started)
    with pytest.raises(InsufficientPermissionError):
        svc.update_leave_log(started.id, payload, owner)
    with pytest.raises(InsufficientPermissionError):
        svc.delete_leave_log(started.id, owner)


@pytest.mark.parametrize(
    "role,sees_reason",
    [
        (UserRole.employee, False),
        (UserRole.manager, True),
        (UserRole.admin, True),
    ],
)
def test_reason_privacy(role, sees_reason):
    owner = make_user(UserRole.employee)
    d = today()
    svc = make_leave_service()
    svc.leave_logs.list_filtered.return_value = [make_leave(owner.id, d, d)]
    (item,) = svc.list_leave_logs(make_user(role), PAGE)
    assert (item.reason == "private") is sees_reason
    assert item.reason is None or sees_reason

    svc.leave_logs.list_filtered.return_value = [make_leave(owner.id, d, d)]
    (own,) = svc.list_leave_logs(owner, PAGE)
    assert own.reason == "private"


def test_leave_list_passes_range_and_pagination():
    svc = make_leave_service()
    d = today()
    svc.list_leave_logs(make_user(), PAGE, from_date=d, to_date=d)
    kw = svc.leave_logs.list_filtered.call_args.kwargs
    assert kw["from_date"] == d and kw["to_date"] == d and kw["limit"] == 50


def test_leave_routes_smoke(make_client):
    client = make_client(UserRole.employee)
    assert (
        client.get("/leave-logs?from_date=2026-01-01&to_date=2026-02-01").status_code
        == 200
    )
    assert (
        client.post(
            "/leave-logs",
            json={
                "start_date": "2026-05-05",
                "end_date": "2026-05-01",
                "leave_type": "sick",
            },
        ).status_code
        == 422
    )


# ---- calendar schema ------------------------------------------------------


def event_kwargs(**kw):
    base = dict(
        title="Standup",
        event_type=CalendarEventType.team_event,
        start_time=T0,
        end_time=T1,
    )
    base.update(kw)
    return base


def test_calendar_schema_validation():
    with pytest.raises(ValidationError):
        CalendarEventCreate(**event_kwargs(end_time=T0 - timedelta(hours=1)))
    with pytest.raises(ValidationError):
        CalendarEventCreate(**event_kwargs(start_time=datetime(2026, 3, 1, 9)))
    with pytest.raises(ValidationError):
        CalendarEventCreate(**event_kwargs(title="x" * 256))
    with pytest.raises(ValidationError):
        CalendarEventCreate(**event_kwargs(title=""))
    for field in ("title", "event_type", "start_time", "end_time"):
        with pytest.raises(ValidationError):
            CalendarEventUpdate(**{field: None})
    with pytest.raises(ValidationError):
        CalendarEventUpdate(start_time=T1, end_time=T0)
    with pytest.raises(ValidationError):
        CalendarEventUpdate(end_time=datetime(2026, 3, 1, 9))
    assert CalendarEventUpdate(description=None).description is None


# ---- calendar service -----------------------------------------------------


def make_event_service(event=None):
    svc = CalendarEventService(MagicMock())
    svc.events = MagicMock()
    svc.events.get_active_by_id.return_value = event
    svc.events.add.side_effect = lambda e: e
    return svc


def make_event(created_by=None, event_type=CalendarEventType.team_event, **kw):
    return SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        created_by=created_by or uuid.uuid4(),
        event_type=event_type,
        source_leave_log_id=None,
        start_time=T0,
        end_time=T1,
        **kw,
    )


@pytest.mark.parametrize(
    "event_type,allowed",
    [
        (CalendarEventType.holiday, {UserRole.admin}),
        (CalendarEventType.milestone, {UserRole.admin, UserRole.manager}),
        (CalendarEventType.release, {UserRole.admin, UserRole.manager}),
        (
            CalendarEventType.team_event,
            {UserRole.admin, UserRole.manager, UserRole.employee},
        ),
        (CalendarEventType.leave, set()),
    ],
)
def test_create_permission_matrix(event_type, allowed):
    payload = CalendarEventCreate(**event_kwargs(event_type=event_type))
    for role in (UserRole.admin, UserRole.manager, UserRole.employee):
        svc = make_event_service()
        if role in allowed:
            event = svc.create_event(payload, make_user(role))
            assert event.event_type == event_type
            svc.db.commit.assert_not_called()
        else:
            with pytest.raises(InsufficientPermissionError):
                svc.create_event(payload, make_user(role))


def test_leave_event_not_creatable_via_route(make_client):
    resp = make_client(UserRole.admin).post(
        "/calendar-events",
        json={
            "title": "x",
            "event_type": "leave",
            "start_time": T0.isoformat(),
            "end_time": T1.isoformat(),
        },
    )
    assert resp.status_code == 403


def test_naive_datetime_is_422_via_route(make_client):
    resp = make_client().post(
        "/calendar-events",
        json={
            "title": "x",
            "event_type": "team_event",
            "start_time": "2026-03-01T09:00:00",
            "end_time": "2026-03-01T10:00:00",
        },
    )
    assert resp.status_code == 422


def test_list_uses_overlap_range_semantics(db):
    from app.repositories.calendar_event_repository import CalendarEventRepository

    CalendarEventRepository(db).list_filtered(
        limit=10, offset=0, range_start=T0, range_end=T1
    )
    sql = str(
        db.scalars.call_args.args[0].compile(compile_kwargs={"literal_binds": False})
    )
    assert "calendar_events.start_time <=" in sql
    assert "calendar_events.end_time >=" in sql
    assert "LIMIT" in sql and "ORDER BY" in sql


def test_update_validates_merged_times():
    creator = make_user(UserRole.employee)
    event = make_event(created_by=creator.id)
    svc = make_event_service(event)
    with pytest.raises(AppException) as exc:
        svc.update_event(
            event.id,
            CalendarEventUpdate(end_time=T0 - timedelta(hours=1)),
            creator,
        )
    assert exc.value.status_code == 422
    svc.update_event(
        event.id, CalendarEventUpdate(end_time=T1 + timedelta(hours=1)), creator
    )
    assert event.end_time == T1 + timedelta(hours=1)


def test_update_cannot_switch_type_to_leave_or_privileged():
    creator = make_user(UserRole.employee)
    event = make_event(created_by=creator.id)
    svc = make_event_service(event)
    for new_type in (CalendarEventType.leave, CalendarEventType.holiday):
        with pytest.raises(InsufficientPermissionError):
            svc.update_event(
                event.id, CalendarEventUpdate(event_type=new_type), creator
            )


def test_edit_delete_admin_or_creator_only():
    creator = make_user(UserRole.employee)
    event = make_event(created_by=creator.id)
    svc = make_event_service(event)
    svc.delete_event(event.id, creator)
    svc.delete_event(event.id, make_user(UserRole.admin))
    for role in (UserRole.employee, UserRole.manager):
        with pytest.raises(InsufficientPermissionError):
            svc.delete_event(event.id, make_user(role))
        with pytest.raises(InsufficientPermissionError):
            svc.update_event(event.id, CalendarEventUpdate(title="n"), make_user(role))


def test_system_leave_events_are_read_only():
    admin = make_user(UserRole.admin)
    event = make_event(created_by=admin.id, event_type=CalendarEventType.leave)
    event.source_leave_log_id = uuid.uuid4()
    svc = make_event_service(event)
    with pytest.raises(InsufficientPermissionError):
        svc.update_event(event.id, CalendarEventUpdate(title="n"), admin)
    with pytest.raises(InsufficientPermissionError):
        svc.delete_event(event.id, admin)
