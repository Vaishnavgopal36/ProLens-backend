"""In-process real-time fan-out for the project discussion.

LIMITATION: ``InProcessConnectionManager`` only reaches sockets connected to the
*same* server process. With several backend processes/replicas, a message
published in one process is not delivered to sockets held by another. To scale
out, add another ``Publisher`` implementation (Postgres LISTEN/NOTIFY or Redis
pub/sub) that publishes to a shared channel and have every process fan out to its
local sockets. See TECH_DEBT.md.

REST handlers are sync (threadpool) while sockets live on the event loop, so
``publish_threadsafe`` schedules the async fan-out on the loop captured at connect.
"""

import asyncio
import logging
import uuid
from typing import Protocol

from fastapi import WebSocket

logger = logging.getLogger(__name__)

MAX_SOCKETS_PER_USER_PROJECT = 5
SEND_TIMEOUT_SECONDS = 5.0
CLOSE_TIMEOUT_SECONDS = 2.0
CLOSE_TOO_MANY = 4409


class Publisher(Protocol):
    def publish_threadsafe(self, project_id: uuid.UUID, event: dict) -> None: ...


class _Connection:
    __slots__ = ("ws", "user_id")

    def __init__(self, ws: WebSocket, user_id: uuid.UUID):
        self.ws = ws
        self.user_id = user_id


class InProcessConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, list[_Connection]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(
        self, project_id: uuid.UUID, user_id: uuid.UUID, ws: WebSocket
    ) -> _Connection:
        """Register an accepted socket; evict the oldest beyond the per-user cap."""
        self._loop = asyncio.get_running_loop()
        conns = self._connections.setdefault(project_id, [])
        conn = _Connection(ws, user_id)
        evicted: list[_Connection] = []
        while sum(1 for c in conns if c.user_id == user_id) >= (
            MAX_SOCKETS_PER_USER_PROJECT
        ):
            oldest = next(c for c in conns if c.user_id == user_id)
            conns.remove(oldest)
            evicted.append(oldest)
        conns.append(conn)
        for old in evicted:
            await self._close(old, CLOSE_TOO_MANY)
        return conn

    def disconnect(self, project_id: uuid.UUID, conn: _Connection) -> None:
        conns = self._connections.get(project_id)
        if conns is None:
            return
        if conn in conns:
            conns.remove(conn)
        if not conns:
            self._connections.pop(project_id, None)

    async def _close(self, conn: _Connection, code: int) -> None:
        try:
            await asyncio.wait_for(conn.ws.close(code=code), CLOSE_TIMEOUT_SECONDS)
        except Exception:  # noqa: BLE001 - already dead is fine
            pass

    async def _send(self, project_id: uuid.UUID, conn: _Connection, event: dict):
        try:
            await asyncio.wait_for(conn.ws.send_json(event), SEND_TIMEOUT_SECONDS)
        except Exception:  # noqa: BLE001 - slow or dead client: drop it
            self.disconnect(project_id, conn)
            await self._close(conn, 1011)

    async def publish(self, project_id: uuid.UUID, event: dict) -> None:
        conns = list(self._connections.get(project_id, ()))
        if conns:
            await asyncio.gather(*(self._send(project_id, c, event) for c in conns))

    def publish_threadsafe(self, project_id: uuid.UUID, event: dict) -> None:
        """Schedule a publish from any thread. Never raises."""
        try:
            loop = self._loop
            if loop is None or loop.is_closed() or not loop.is_running():
                return
            future = asyncio.run_coroutine_threadsafe(
                self.publish(project_id, event), loop
            )
            future.add_done_callback(_log_failure)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to schedule discussion publish")


def _log_failure(future) -> None:
    if not future.cancelled() and future.exception() is not None:
        logger.error("Discussion publish failed", exc_info=future.exception())


manager = InProcessConnectionManager()
