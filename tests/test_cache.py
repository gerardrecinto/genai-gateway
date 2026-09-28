import time

import pytest

from genai_gateway.cache.cache_backend import InMemoryCache, RedisCache, get_cache_backend


def test_in_memory_cache_set_and_get():
    cache = InMemoryCache()
    cache.set("k", "v", ttl_seconds=60)
    assert cache.get("k") == "v"


def test_in_memory_cache_expires():
    cache = InMemoryCache()
    cache.set("k", "v", ttl_seconds=0)
    time.sleep(0.01)
    assert cache.get("k") is None


def test_in_memory_cache_miss_returns_none():
    cache = InMemoryCache()
    assert cache.get("missing") is None


def test_get_cache_backend_falls_back_to_in_memory_on_bad_url():
    backend = get_cache_backend("redis://localhost:1")  # nothing listening
    assert isinstance(backend, InMemoryCache)


def test_get_cache_backend_returns_in_memory_when_no_url():
    backend = get_cache_backend(None)
    assert isinstance(backend, InMemoryCache)


@pytest.fixture
def redis_cache():
    try:
        cache = RedisCache("redis://localhost:6379")
    except Exception:
        pytest.skip("local Redis not reachable at redis://localhost:6379 (docker compose up -d redis)")
    yield cache


def test_redis_cache_set_and_get(redis_cache):
    key = "genai-gateway:test:set-get"
    redis_cache.set(key, "hello-from-test", ttl_seconds=30)
    assert redis_cache.get(key) == "hello-from-test"


def test_redis_cache_miss_returns_none(redis_cache):
    assert redis_cache.get("genai-gateway:test:definitely-not-set") is None


def test_get_cache_backend_returns_redis_cache_when_reachable():
    backend = get_cache_backend("redis://localhost:6379")
    assert isinstance(backend, RedisCache)
