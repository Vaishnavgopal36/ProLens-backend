import asyncio
import json
import logging
import time
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.api.deps import authenticate_access_token
from app.core import realtime
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.exception import InvalidCredentialsAuthError, ProjectNotFoundError
from app.services.discussion_service import DiscussionService

logger = logging.getLogger(__name__)

router = APIRouter()

CLOSE_UNAUTHENTICATED = 4401
CLOSE_FORBIDDEN_ORIGIN = 4403
CLOSE_NO_ACCESS = 4404
CLOSE_TOO_BIG = 1009
MAX_FRAME_BYTES = 1024


def _authorize(
    token: str | None, project_id: uuid.UUID
) -> tuple[float | None, uuid.UUID]:
    """Authenticate + authorize with a short-lived session, closed before returning.

    Returns (token ``exp`` in epoch seconds or None, user id).
    """
    db = SessionLocal()
    try:
        user, payload = authenticate_access_token(token, db)
        DiscussionService(db)._get_accessible_project(project_id, user)
        exp = payload.get("exp")
        return (float(exp) if exp is not None else None, user.id)
    finally:
        db.close()


@router.websocket("/ws/projects/{project_id}/discussion")
async def discussion_socket(websocket: WebSocket, project_id: uuid.UUID) -> None:
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in settings.CORS_ALLOWED_ORIGINS:
        await websocket.close(code=CLOSE_FORBIDDEN_ORIGIN)
        return

    try:
        exp, user_id = await run_in_threadpool(
            _authorize, websocket.cookies.get("access_token"), project_id
        )
    except InvalidCredentialsAuthError:
        await websocket.close(code=CLOSE_UNAUTHENTICATED)
        return
    except ProjectNotFoundError:
        await websocket.close(code=CLOSE_NO_ACCESS)
        return
    except Exception:  # noqa: BLE001
        logger.exception("Discussion socket authorization failed")
        await websocket.close(code=CLOSE_UNAUTHENTICATED)
        return

    await websocket.accept()
    conn = await realtime.manager.connect(project_id, user_id, websocket)
    try:
        await websocket.send_json({"type": "ready"})
        while True:
            remaining = None if exp is None else exp - time.time()
            if remaining is not None and remaining <= 0:
                await websocket.close(code=CLOSE_UNAUTHENTICATED)
                return
            try:
                text = await asyncio.wait_for(websocket.receive_text(), remaining)
            except asyncio.TimeoutError:
                await websocket.close(code=CLOSE_UNAUTHENTICATED)
                return
            if len(text.encode("utf-8")) > MAX_FRAME_BYTES:
                await websocket.close(code=CLOSE_TOO_BIG)
                return
            try:
                frame = json.loads(text)
            except ValueError:
                continue
            if isinstance(frame, dict) and frame.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        realtime.manager.disconnect(project_id, conn)
