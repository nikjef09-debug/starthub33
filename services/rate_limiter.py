"""Простой in-memory rate limiter для защиты auth-эндпоинтов."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException


class _RateLimiter:
    def __init__(self):
        self._buckets: dict[str, deque] = defaultdict(deque)

    def is_allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        bucket = self._buckets[key]
        while bucket and bucket[0] < now - window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


_limiter = _RateLimiter()


async def check_rate_limit(key: str, limit: int, window: int, enabled: bool = True) -> None:
    """Raise HTTP 429 if rate limit exceeded. No-op when enabled=False."""
    if not enabled:
        return
    if not _limiter.is_allowed(key, limit, window):
        raise HTTPException(
            status_code=429,
            detail="Слишком много запросов. Подождите немного и повторите.",
        )
