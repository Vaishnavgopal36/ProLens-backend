"""In-memory sliding-window rate limiter.

NOTE: state lives in this process only. With several uvicorn workers or
replicas each process keeps its own counters, so the effective limit is
``attempts * processes``. Use a shared store (Redis) if strict limits are needed.
"""

import threading
import time
from collections import defaultdict, deque

from app.core.config import settings
from app.core.exception import AppException


class SlidingWindowRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: float) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window_seconds:
            hits.popleft()
        if not hits:
            self._hits.pop(key, None)
        return hits

    def is_limited(self, key: str) -> bool:
        with self._lock:
            return len(self._prune(key, time.monotonic())) >= self.max_attempts

    def check(self, key: str) -> None:
        """Raise 429 when ``key`` already used up its attempts in the window."""
        if self.is_limited(key):
            raise AppException(
                "Too many login attempts. Please try again later.",
                status_code=429,
                status_message="Too Many Requests",
            )

    def record(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._prune(key, now)
            self._hits[key].append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


login_rate_limiter = SlidingWindowRateLimiter(
    settings.LOGIN_RATE_LIMIT_ATTEMPTS, settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS
)
