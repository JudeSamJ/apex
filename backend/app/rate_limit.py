import os
import time
import logging
from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# In-memory sliding window cache: key -> list of timestamps. This is the
# fallback used when Redis isn't configured (e.g. local dev/tests) and is
# also what test_hardening.py's clean_history fixture resets between tests.
# It only rate-limits within a single process — see _get_redis_client below
# for why that's not safe once you run more than one API instance.
_request_history: Dict[str, List[float]] = defaultdict(list)

REDIS_URL = os.getenv("REDIS_URL", "")

_redis_client = None
_redis_unavailable_logged = False


def _get_redis_client():
    """Lazily build (and cache) a Redis client if REDIS_URL points at a real
    broker. Returns None — and callers fall back to the in-memory limiter —
    if no URL is configured, the redis package isn't installed, or the
    connection fails. The in-memory limiter only rate-limits per-process, so
    it under-counts once the API runs behind more than one instance; Redis
    is what makes the limit actually global.
    """
    global _redis_client, _redis_unavailable_logged

    if not REDIS_URL.startswith(("redis://", "rediss://")):
        return None

    if _redis_client is not None:
        return _redis_client

    try:
        import redis
        client = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        _redis_client = client
        return _redis_client
    except Exception as e:
        if not _redis_unavailable_logged:
            logger.warning(f"Redis rate limiter unavailable ({e}); falling back to in-memory rate limiting")
            _redis_unavailable_logged = True
        return None


def _check_rate_limit_redis(client, key: str, limit: int, window_seconds: int) -> bool:
    """Sliding-window rate limit backed by a Redis sorted set, shared across
    every API process. Returns True if the request is allowed."""
    now = time.time()
    cutoff = now - window_seconds

    pipe = client.pipeline()
    pipe.zremrangebyscore(key, 0, cutoff)
    pipe.zcard(key)
    _, count = pipe.execute()

    if count >= limit:
        return False

    pipe = client.pipeline()
    pipe.zadd(key, {f"{now}:{os.urandom(4).hex()}": now})
    pipe.expire(key, window_seconds)
    pipe.execute()
    return True


def _check_rate_limit_in_memory(key: str, limit: int, window_seconds: int) -> bool:
    now = time.time()
    cutoff = now - window_seconds

    _request_history[key] = [t for t in _request_history[key] if t > cutoff]

    if len(_request_history[key]) >= limit:
        return False

    _request_history[key].append(now)
    return True


def check_rate_limit(user_id: str, endpoint: str, limit: int = 10, window_seconds: int = 60):
    """Sliding-window rate limiter for mutate endpoints.

    Uses Redis (shared across every API process) when REDIS_URL is configured
    and reachable; otherwise falls back to a per-process in-memory window, so
    local dev and tests keep working with zero setup. Raises HTTPException
    429 if the caller exceeds `limit` requests in the last `window_seconds`.
    """
    key = f"ratelimit:{user_id}:{endpoint}"

    redis_client = _get_redis_client()
    if redis_client is not None:
        try:
            allowed = _check_rate_limit_redis(redis_client, key, limit, window_seconds)
        except Exception as e:
            logger.warning(f"Redis rate limiter call failed ({e}); falling back to in-memory for this request")
            allowed = _check_rate_limit_in_memory(key, limit, window_seconds)
    else:
        allowed = _check_rate_limit_in_memory(key, limit, window_seconds)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait before executing further state modifications."
        )
