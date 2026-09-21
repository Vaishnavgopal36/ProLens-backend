import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.exception import ProjectNotFoundError
from app.models.enums import UserRole
from app.schemas.discussion import DiscussionCreate
from app.services.discussion_service import (
    DiscussionService,
    InvalidCursorError,
    author_initials,
    decode_cursor,
    encode_cursor,
    to_message,
)
from tests.conftest import ORG_ID, make_user

NOW = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)


def make_author(first="Ada", last="Lovelace", email="ada@example.com"):
    return SimpleNamespace(
        id=uuid.uuid4(), first_name=first, last_name=last, email=email
    )


def make_msg(minutes=0, author=None, updated_delta=0, project_id=None):
    created = NOW + timedelta(minutes=minutes)
    return SimpleNamespace(
        id=uuid.uuid4(),
        project_id=project_id or uuid.uuid4(),
        author=author or make_author(),
        content="hello",
        created_at=created,
        updated_at=created + timedelta(seconds=updated_delta),
    )


def make_service(project="default", member=True):
    svc = DiscussionService(MagicMock())
    if project == "default":
        project = SimpleNamespace(id=uuid.uuid4(), organization_id=ORG_ID)
    svc.projects = MagicMock()
    svc.projects.get_active_by_id.return_value = project
    svc.projects.is_member.return_value = member
    svc.discussion = MagicMock()
    svc.discussion.add.side_effect = lambda c: c
    svc.discussion.upsert_read.return_value = NOW
    return svc


# ---- cursor ---------------------------------------------------------------


def test_cursor_round_trip():
    cid = uuid.uuid4()
    assert decode_cursor(encode_cursor(NOW, cid)) == (NOW, cid)


@pytest.mark.parametrize("bad", ["!!!", "bm90LWEtY3Vyc29y", "", "YXxi"])
def test_invalid_cursor_is_422(bad):
    with pytest.raises(InvalidCursorError) as exc:
        decode_cursor(bad)
    assert exc.value.status_code == 422


# ---- paging ---------------------------------------------------------------


def test_first_page_has_more_and_next_cursor():
    svc = make_service()
    rows = [make_msg(minutes=-i) for i in range(4)]  # limit 3 -> 4 rows
    svc.discussion.list_page.return_value = rows
    page = svc.list_messages(uuid.uuid4(), make_user(), limit=3, before=None)
    assert svc.discussion.list_page.call_args.kwargs["limit"] == 4
    assert svc.discussion.list_page.call_args.kwargs["before"] is None
    assert len(page.items) == 3 and page.has_more
    assert decode_cursor(page.next_cursor) == (rows[2].created_at, rows[2].id)


def test_before_page_last_page_has_no_more():
    svc = make_service()
    rows = [make_msg(minutes=-i) for i in range(2)]
    svc.discussion.list_page.return_value = rows
    cursor = encode_cursor(NOW, uuid.uuid4())
    page = svc.list_messages(uuid.uuid4(), make_user(), limit=3, before=cursor)
    assert svc.discussion.list_page.call_args.kwargs["before"] == decode_cursor(cursor)
    assert len(page.items) == 2
    assert page.has_more is False and page.next_cursor is None


def test_exactly_limit_rows_is_not_more():
    svc = make_service()
    svc.discussion.list_page.return_value = [make_msg(minutes=-i) for i in range(3)]
    page = svc.list_messages(uuid.uuid4(), make_user(), limit=3, before=None)
    assert not page.has_more and page.next_cursor is None


def test_bad_cursor_rejected_by_service():
    svc = make_service()
    with pytest.raises(InvalidCursorError):
        svc.list_messages(uuid.uuid4(), make_user(), limit=3, before="garbage!")


# ---- authorization --------------------------------------------------------


def test_non_member_employee_gets_404():
    svc = make_service(member=False)
    svc.discussion.list_page.return_value = []
    with pytest.raises(ProjectNotFoundError):
        svc.list_messages(uuid.uuid4(), make_user(UserRole.employee), 30, None)


def test_member_employee_allowed():
    svc = make_service(member=True)
    svc.discussion.list_page.return_value = []
    svc.list_messages(uuid.uuid4(), make_user(UserRole.employee), 30, None)


def test_admin_allowed_without_membership():
    svc = make_service(member=False)
    svc.discussion.list_page.return_value = []
    svc.list_messages(uuid.uuid4(), make_user(UserRole.admin), 30, None)


def test_other_org_and_missing_and_deleted_project_not_found():
    other = SimpleNamespace(id=uuid.uuid4(), organization_id=uuid.uuid4())
    for project in (other, None):
        svc = make_service(project=project, member=True)
        with pytest.raises(ProjectNotFoundError):
            svc.list_messages(uuid.uuid4(), make_user(UserRole.admin), 30, None)


# ---- create / unread / read -----------------------------------------------


def test_create_marks_read_for_author():
    svc = make_service()
    caller = make_user()
    caller.first_name, caller.last_name = "Bob", "Ross"
    pid = uuid.uuid4()
    comment_holder = {}

    def add(c):
        c.id = uuid.uuid4()
        c.created_at = NOW
        c.updated_at = NOW
        comment_holder["c"] = c
        return c

    svc.discussion.add.side_effect = add
    msg = svc.post_message(pid, DiscussionCreate(content="  hi  "), caller)
    c = comment_holder["c"]
    assert c.project_id == pid and c.parent_comment_id is None
    assert c.organization_id == ORG_ID and c.author_id == caller.id
    assert msg.content == "hi" and msg.author.name == "Bob Ross" and not msg.edited
    kw = svc.discussion.upsert_read.call_args.kwargs
    assert kw["user_id"] == caller.id and kw["project_id"] == pid


def test_unread_passes_caller_and_last_read():
    svc = make_service()
    caller = make_user()
    svc.discussion.get_last_read_at.return_value = NOW
    svc.discussion.count_unread.return_value = 7
    res = svc.unread(uuid.uuid4(), caller)
    assert res.unread_count == 7 and res.last_read_at == NOW
    kw = svc.discussion.count_unread.call_args.kwargs
    assert kw["user_id"] == caller.id and kw["last_read_at"] == NOW


def test_unread_never_read_counts_all():
    svc = make_service()
    svc.discussion.get_last_read_at.return_value = None
    svc.discussion.count_unread.return_value = 3
    res = svc.unread(uuid.uuid4(), make_user())
    assert res.unread_count == 3 and res.last_read_at is None
    assert svc.discussion.count_unread.call_args.kwargs["last_read_at"] is None


def test_count_unread_query_excludes_own_and_deleted():
    from app.repositories.discussion_repository import DiscussionRepository

    db = MagicMock()
    db.scalar.return_value = 2
    repo = DiscussionRepository(db)
    assert (
        repo.count_unread(
            project_id=uuid.uuid4(), user_id=uuid.uuid4(), last_read_at=NOW
        )
        == 2
    )
    sql = str(db.scalar.call_args.args[0])
    assert "author_id !=" in sql and "deleted_at IS NULL" in sql
    assert "created_at >" in sql


def test_mark_read_upserts():
    svc = make_service()
    caller = make_user()
    pid = uuid.uuid4()
    res = svc.mark_read(pid, caller)
    assert res.last_read_at == NOW
    kw = svc.discussion.upsert_read.call_args.kwargs
    assert kw["organization_id"] == ORG_ID and kw["project_id"] == pid


def test_mark_read_requires_access():
    svc = make_service(member=False)
    with pytest.raises(ProjectNotFoundError):
        svc.mark_read(uuid.uuid4(), make_user())


# ---- message mapping ------------------------------------------------------


def test_author_name_and_initials_fallbacks():
    m = to_message(make_msg(author=make_author("Ada", "Lovelace")))
    assert (m.author.name, m.author.initials) == ("Ada Lovelace", "AL")
    m = to_message(make_msg(author=make_author("Ada", None)))
    assert (m.author.name, m.author.initials) == ("Ada", "A")
    m = to_message(make_msg(author=make_author(None, None, "john.doe@x.com")))
    assert (m.author.name, m.author.initials) == ("john.doe", "JD")
    m = to_message(make_msg(author=make_author(None, None, "zed@x.com")))
    assert (m.author.name, m.author.initials) == ("zed", "Z")
    assert author_initials("a b c") == "AB"


def test_edited_flag():
    assert not to_message(make_msg(updated_delta=0)).edited
    assert to_message(make_msg(updated_delta=30)).edited
    row = make_msg()
    row.updated_at = None
    assert not to_message(row).edited


# ---- routes ---------------------------------------------------------------


def test_routes_limit_bounds_and_cursor(make_client):
    client = make_client()
    pid = uuid.uuid4()
    base = f"/projects/{pid}/discussion"
    assert client.get(f"{base}?limit=0").status_code == 422
    assert client.get(f"{base}?limit=101").status_code == 422
    # project missing in the mocked DB -> 404 for valid params
    assert client.get(f"{base}?limit=100").status_code == 404
    assert client.get(f"{base}/unread").status_code == 404
    assert client.post(f"{base}/read").status_code == 404
    assert client.post(base, json={"content": "hi"}).status_code == 404
    assert client.post(base, json={"content": "   "}).status_code == 422
    assert client.post(base, json={"content": "x" * 10_001}).status_code == 422


def test_route_invalid_cursor_422(make_client, db, monkeypatch):
    from app.repositories.project_repository import ProjectRepository

    client = make_client(UserRole.admin)
    project = SimpleNamespace(id=uuid.uuid4(), organization_id=ORG_ID)
    monkeypatch.setattr(
        ProjectRepository, "get_active_by_id", lambda self, pid: project
    )
    res = client.get(f"/projects/{project.id}/discussion?before=not-a-cursor")
    assert res.status_code == 422
