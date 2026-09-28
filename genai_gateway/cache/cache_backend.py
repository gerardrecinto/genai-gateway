"""Cache abstraction with two backends behind one interface: in-memory
(default, no external dependency) and Redis (used when REDIS_URL is set
and reachable). The gateway code never branches on which backend is
active — that's the point of the abstraction.
"""

import time
from typing import Protocol


class CacheBackend(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ttl_seconds: int) -> None: ...


class InMemoryCache:
    """Process-local cache. Fine for local dev and tests; does not share
    state across multiple gateway processes — that's what RedisCache is for.
    """

    def __init__(self):
        self._store: dict[str, tuple[str, float]] = {}

    def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._store[key] = (value, time.monotonic() + ttl_seconds)


class RedisCache:
    def __init__(self, redis_url: str):
        import redis  # deferred import: only needed when this backend is used

        self._client = redis.Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        self._client.ping()  # fail fast at construction time, not on first request

    def get(self, key: str) -> str | None:
        value = self._client.get(key)
        return value.decode("utf-8") if value is not None else None

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._client.set(key, value, ex=ttl_seconds)


def get_cache_backend(redis_url: str | None) -> CacheBackend:
    if not redis_url:
        return InMemoryCache()
    try:
        return RedisCache(redis_url)
    except Exception:
        # Redis configured but unreachable: degrade to in-memory rather than
        # fail every request. Caching is a performance optimization here,
        # not a correctness requirement, so failing open is the right call.
        return InMemoryCache()
