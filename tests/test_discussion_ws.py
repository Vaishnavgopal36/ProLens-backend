import asyncio
import contextlib
import threading
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.routes import discussion_ws
from app.core import realtime
from app.core.config import settings
from app.core.exception import InvalidCredentialsAuthError, ProjectNotFoundError
from app.main import app
from app.schemas.discussion import DiscussionAuthor, DiscussionMessage
from app.services.comment_service import CommentService
from app.services.discussion_service import DiscussionService
from tests.conftest import make_user

ALLOWED = settings.CORS_ALLOWED_ORIGINS[0]
PROJECT = uuid.uuid4()
OTHER_PROJECT = uuid.uuid4()
NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fresh_manager(monkeypatch):
    mgr = realtime.InProcessConnectionManager()
    monkeypatch.setattr(realtime, "manager", mgr)
    return mgr


@pytest.fixture
def auth(monkeypatch):
    """Patch _authorize; state['error'] / state['user'] / state['exp'] steer it."""
    state = {"error": None, "user": uuid.uuid4(), "exp": None}

    def fake(token, project_id):
        if state["error"] is not None:
            raise state["error"]
        return state["exp"], state["user"]

    monkeypatch.setattr(discussion_ws, "_authorize", fake)
    return state


@pytest.fixture
def client(auth):
    with TestClient(app) as c:
        yield c


def url(project=PROJECT):
    return f"/ws/projects/{project}/discussion"


def event(n="x"):
    return {"type": "message.created", "data": {"id": n}}


# ---- handshake ------------------------------------------------------------


def test_unauthenticated_rejected(client, auth):
    auth["error"] = InvalidCredentialsAuthError()
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(url()):
            pass
    assert exc.value.code in (4401, 403)


def test_no_access_rejected(client, auth):
    auth["error"] = ProjectNotFoundError()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(url()):
            pass


def test_disallowed_origin_rejected(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(url(), headers={"origin": "https://evil.test"}):
            pass


def test_allowed_and_absent_origin_accepted(client):
    with client.websocket_connect(url(), headers={"origin": ALLOWED}) as ws:
        assert ws.receive_json() == {"type": "ready"}
    with client.websocket_connect(url()) as ws:
        assert ws.receive_json() == {"type": "ready"}


def test_ping_pong_and_ignored_frames(client):
    with client.websocket_connect(url()) as ws:
        ws.receive_json()
        ws.send_text("not json")
        ws.send_json({"type": "hello"})
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_authorize_closes_session_and_sets_up_via_shared_helper(monkeypatch):
    db = MagicMock()
    user = make_user()
    monkeypatch.setattr(discussion_ws, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        discussion_ws,
        "authenticate_access_token",
        lambda token, session: (user, {"exp": 123}),
    )
    seen = {}
    monkeypatch.setattr(
        DiscussionService,
        "_get_accessible_project",
        lambda self, pid, caller: seen.update(pid=pid, caller=caller),
    )
    assert discussion_ws._authorize("tok", PROJECT) == (123.0, user.id)
    assert seen == {"pid": PROJECT, "caller": user}
    db.close.assert_called_once()

    def boom(self, pid, caller):
        raise ProjectNotFoundError()

    monkeypatch.setattr(DiscussionService, "_get_accessible_project", boom)
    db.close.reset_mock()
    with pytest.raises(ProjectNotFoundError):
        discussion_ws._authorize("tok", PROJECT)
    db.close.assert_called_once()


# ---- limits ---------------------------------------------------------------


def test_oversize_frame_closes_1009(client):
    with client.websocket_connect(url()) as ws:
        ws.receive_json()
        ws.send_text("x" * 2000)
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 1009


def test_sixth_connection_closes_oldest_4409(client):
    with contextlib.ExitStack() as stack:
        sockets = []
        for _ in range(5):
            ws = stack.enter_context(client.websocket_connect(url()))
            ws.receive_json()
            sockets.append(ws)
        sixth = stack.enter_context(client.websocket_connect(url()))
        assert sixth.receive_json() == {"type": "ready"}
        with pytest.raises(WebSocketDisconnect) as exc:
            sockets[0].receive_json()
        assert exc.value.code == 4409


def test_closes_4401_when_token_expires(client, auth):
    auth["exp"] = time.time() + 0.4
    with client.websocket_connect(url()) as ws:
        ws.receive_json()
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4401


# ---- fan-out --------------------------------------------------------------


def test_publish_threadsafe_scoped_to_project(client, fresh_manager):
    with (
        client.websocket_connect(url()) as a,
        client.websocket_connect(url()) as b,
        client.websocket_connect(url(OTHER_PROJECT)) as other,
    ):
        for ws in (a, b, other):
            ws.receive_json()
        t = threading.Thread(
            target=realtime.manager.publish_threadsafe, args=(PROJECT, event("1"))
        )
        t.start()
        t.join()
        assert a.receive_json() == event("1")
        assert b.receive_json() == event("1")
        # the other project's socket gets nothing: next frame is its own pong
        other.send_json({"type": "ping"})
        assert other.receive_json() == {"type": "pong"}


def test_publish_without_loop_is_noop():
    realtime.InProcessConnectionManager().publish_threadsafe(PROJECT, event())


def test_dead_socket_dropped_without_breaking_others():
    class Good:
        def __init__(self):
            self.sent = []

        async def send_json(self, e):
            self.sent.append(e)

        async def close(self, code=1000):
            pass

    class Dead(Good):
        async def send_json(self, e):
            raise RuntimeError("closed")

    class Slow(Good):
        async def send_json(self, e):
            await asyncio.sleep(10)

    async def run():
        mgr = realtime.InProcessConnectionManager()
        realtime.SEND_TIMEOUT_SECONDS = 0.1
        good, dead, slow = Good(), Dead(), Slow()
        uid = uuid.uuid4()
        for s in (dead, slow, good):
            await mgr.connect(PROJECT, uid, s)
        await mgr.publish(PROJECT, event())
        assert good.sent == [event()]
        remaining = [c.ws for c in mgr._connections[PROJECT]]
        assert remaining == [good]

    old = realtime.SEND_TIMEOUT_SECONDS
    try:
        asyncio.run(run())
    finally:
        realtime.SEND_TIMEOUT_SECONDS = old


# ---- REST broadcast -------------------------------------------------------


def make_message(project_id=PROJECT):
    return DiscussionMessage(
        id=uuid.uuid4(),
        project_id=project_id,
        author=DiscussionAuthor(id=uuid.uuid4(), name="Ada L", initials="AL"),
        content="hi",
        created_at=NOW,
        edited=False,
    )


@pytest.fixture
def calls(monkeypatch, db):
    log = []
    db.commit.side_effect = lambda: log.append("commit")
    monkeypatch.setattr(
        realtime.manager,
        "publish_threadsafe",
        lambda pid, ev: log.append(("publish", pid, ev)),
    )
    return log


def test_post_publishes_after_commit(make_client, monkeypatch, calls):
    client = make_client()
    msg = make_message()
    monkeypatch.setattr(DiscussionService, "post_message", lambda *a, **k: msg)
    res = client.post(f"/projects/{PROJECT}/discussion", json={"content": "hi"})
    assert res.status_code == 201
    assert calls[0] == "commit"
    assert calls[1] == (
        "publish",
        PROJECT,
        {"type": "message.created", "data": msg.model_dump(mode="json")},
    )


def test_post_not_published_when_commit_fails(make_client, monkeypatch, calls, db):
    client = make_client()
    monkeypatch.setattr(
        DiscussionService, "post_message", lambda *a, **k: make_message()
    )
    db.commit.side_effect = RuntimeError("db down")
    res = client.post(f"/projects/{PROJECT}/discussion", json={"content": "hi"})
    assert res.status_code == 500
    assert not any(isinstance(c, tuple) for c in calls)


def test_publish_errors_do_not_fail_rest(make_client, monkeypatch, db):
    def boom(pid, ev):
        raise RuntimeError("nope")

    monkeypatch.setattr(realtime.manager, "publish_threadsafe", boom)
    client = make_client()
    monkeypatch.setattr(
        DiscussionService, "post_message", lambda *a, **k: make_message()
    )
    res = client.post(f"/projects/{PROJECT}/discussion", json={"content": "hi"})
    assert res.status_code == 201


def make_comment(project_id=PROJECT):
    return SimpleNamespace(
        id=uuid.uuid4(),
        project_id=project_id,
        author=SimpleNamespace(
            id=uuid.uuid4(), first_name="Ada", last_name="L", email="a@x.com"
        ),
        content="edited",
        created_at=NOW,
        updated_at=NOW,
    )


def test_comment_patch_and_delete_broadcast_for_project_comments(
    make_client, monkeypatch, calls
):
    client = make_client()
    comment = make_comment()
    monkeypatch.setattr(CommentService, "update_comment", lambda *a, **k: comment)
    monkeypatch.setattr(CommentService, "delete_comment", lambda *a, **k: comment)
    # Response serialisation is not under test here.
    from app.api.routes import comments as comments_route

    for route in comments_route.router.routes:
        monkeypatch.setattr(route, "response_model", None, raising=False)
        monkeypatch.setattr(route, "response_field", None, raising=False)
    client.patch(f"/comments/{comment.id}", json={"content": "edited"})
    assert calls[0] == "commit"
    kind, pid, ev = calls[1]
    assert (kind, pid, ev["type"]) == ("publish", PROJECT, "message.updated")
    assert ev["data"]["id"] == str(comment.id) and ev["data"]["edited"] is False
    client.delete(f"/comments/{comment.id}")
    assert calls[2] == "commit"
    assert calls[3] == (
        "publish",
        PROJECT,
        {
            "type": "message.deleted",
            "data": {"id": str(comment.id), "project_id": str(PROJECT)},
        },
    )


def test_comment_events_skipped_for_non_project_comments(
    make_client, monkeypatch, calls
):
    client = make_client()
    comment = make_comment(project_id=None)
    monkeypatch.setattr(CommentService, "update_comment", lambda *a, **k: comment)
    monkeypatch.setattr(CommentService, "delete_comment", lambda *a, **k: comment)
    client.patch(f"/comments/{comment.id}", json={"content": "edited"})
    client.delete(f"/comments/{comment.id}")
    assert calls == ["commit", "commit"]
