import pytest

from app.providers.memory import MemoryLock


@pytest.mark.asyncio
async def test_memory_lock_token_match():
    lock = MemoryLock()
    assert await lock.acquire("lock:test", 10, "t1") is True
    assert await lock.acquire("lock:test", 10, "t2") is False
    assert await lock.release("lock:test", "wrong") is False
    assert await lock.release("lock:test", "t1") is True
    assert await lock.acquire("lock:test", 10, "t2") is True


@pytest.mark.asyncio
async def test_redis_lock_if_available():
    redis_url = "redis://localhost:6379/15"
    try:
        from redis.asyncio import from_url

        r = from_url(redis_url, decode_responses=True)
        await r.ping()
    except Exception:
        pytest.skip("Redis not available")

    from app.providers.redis_adapters import RedisLock

    lock = RedisLock(r)
    key = "lock:bb:w2:test"
    await r.delete(key)
    assert await lock.acquire(key, 5, "tok-a") is True
    assert await lock.acquire(key, 5, "tok-b") is False
    assert await lock.release(key, "tok-b") is False
    assert await lock.release(key, "tok-a") is True
    await r.aclose()
