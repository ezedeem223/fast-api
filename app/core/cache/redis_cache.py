"""Redis cache facade with graceful degradation.

Features:
- Async Redis client with optional compression, tag-based invalidation, and batch helpers.
- Stampede protection via per-key asyncio locks.
- In-memory fallback store when Redis is missing/uninitialized to keep tests and degraded mode running.
"""

import json
import logging
import hashlib
import functools
from typing import Any, Optional, Dict
import time
import base64
import zlib
import asyncio

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisCache:
    """Async Redis cache facade with graceful fallback when Redis is unavailable or stubbed."""
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self.enabled = False
        self.default_ttl = 300  # 5 minutes default
        self.ttl_overrides: Dict[str, int] = {
            "comments:list": 120,
            "user_settings": 3600,
        }
        self._compression_threshold = 1024  # bytes
        self._locks: Dict[str, asyncio.Lock] = {}
        self.failed_init = False  # track init failures for test env readiness
        # Lightweight in-memory fallback store used when a provided redis-like object
        # does not implement get/set (e.g., certain test doubles).
        self._fallback_store: dict[str, tuple[Any, Optional[float]]] = {}

    async def init_cache(self):
        """Initialize Redis connection pool."""
        try:
            if not settings.redis_url:
                # Fail open: leave caching disabled instead of blocking app startup when Redis is not configured.
                logger.warning("REDIS_URL not set. Caching disabled.")
                return

            self.redis = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=5,
            )
            # Test connection
            await self.redis.ping()
            self.enabled = True
            self.failed_init = False
            logger.info("Redis cache initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Redis cache: {e}")
            self.enabled = False
            self.failed_init = True

    async def close(self):
        """Close Redis connection."""
        if not self.redis:
            self.failed_init = False
            return
        close_method = getattr(self.redis, "aclose", None) or getattr(
            self.redis, "close", None
        )
        if close_method:
            result = close_method()
            if asyncio.iscoroutine(result):
                await result
        self.redis = None
        self.failed_init = False

    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate a unique cache key based on arguments."""
        # Filter out arguments that shouldn't affect the key (like Request, Session, BackgroundTasks)
        filtered_kwargs = {
            k: v
            for k, v in kwargs.items()
            if not hasattr(v, "__dict__") and not k.startswith("_")
        }

        key_data = json.dumps(
            {"args": args, "kwargs": filtered_kwargs}, sort_keys=True, default=str
        )
        hashed = hashlib.md5(key_data.encode()).hexdigest()
        return f"{prefix}:{hashed}"

    async def get(self, key: str) -> Any:
        """Get value from cache (respects in-memory fallback when Redis is stubbed)."""
        if not self.enabled or not self.redis:
            return None
        # Fallback to in-memory store when the backend stub lacks required APIs.
        if not hasattr(self.redis, "get"):
            expiry = self._fallback_store.get(key)
            if not expiry:
                return None
            value, exp_ts = expiry
            if exp_ts is not None and exp_ts < time.time():
                self._fallback_store.pop(key, None)
                return None
            return value
        try:
            data = await self.redis.get(key)
            if not data:
                return None
            return self._decode_value(data)
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: int = None) -> None:
        """Set value with optional TTL; stores in fallback when Redis backend is absent."""
        if not self.enabled or not self.redis:
            return
        # Fallback path for simple stubs without set()
        if not hasattr(self.redis, "set"):
            exp_ts = (time.time() + (ttl or self.default_ttl)) if (ttl or self.default_ttl) else None
            self._fallback_store[key] = (value, exp_ts)
            return
        try:
            serialized = self._encode_value(value)
            await self.redis.set(key, serialized, ex=self._resolve_ttl(key, ttl))
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")

    async def delete(self, key: str) -> None:
        """Delete a specific key."""
        if not self.enabled or not self.redis:
            return
        try:
            await self.redis.delete(key)
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")

    async def invalidate(self, pattern: str) -> None:
        """
        Invalidate all keys matching a pattern.
        Example: invalidate("posts:list:*")
        """
        if not self.enabled or not self.redis:
            return
        try:
            # Use SCAN instead of KEYS for performance in production
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                if keys:
                    await self.redis.delete(*keys)
                if cursor == 0:
                    break
            logger.info(f"Invalidated cache pattern: {pattern}")
        except Exception as e:
            logger.error(f"Cache invalidation error for pattern {pattern}: {e}")

    async def set_many(self, items: dict, ttl: int = None) -> None:
        """Set multiple key-value pairs at once."""
        if not self.enabled or not self.redis:
            return
        try:
            pipe = self.redis.pipeline()
            for key, value in items.items():
                serialized = self._encode_value(value)
                pipe.set(key, serialized, ex=self._resolve_ttl(key, ttl))
            await pipe.execute()
        except Exception as e:
            logger.error(f"Cache set_many error: {e}")

    async def get_many(self, keys: list) -> dict:
        """Get multiple values at once."""
        if not self.enabled or not self.redis:
            return {}
        try:
            pipe = self.redis.pipeline()
            for key in keys:
                pipe.get(key)
            results = await pipe.execute()

            return {
                key: self._decode_value(value) if value else None
                for key, value in zip(keys, results)
            }
        except Exception as e:
            logger.error(f"Cache get_many error: {e}")
            return {}

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        if not self.enabled or not self.redis:
            return False
        try:
            return await self.redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False

    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment a counter in cache."""
        if not self.enabled or not self.redis:
            return 0
        try:
            return await self.redis.incrby(key, amount)
        except Exception as e:
            logger.error(f"Cache increment error for key {key}: {e}")
            return 0

    async def set_with_tags(
        self, key: str, value: Any, tags: list, ttl: int = None
    ) -> None:
        """Set a value with associated tags for grouped invalidation."""
        if not self.enabled or not self.redis:
            return
        try:
            # Store the actual value
            await self.set(key, value, ttl)

            # Store tag associations
            pipe = self.redis.pipeline()
            for tag in tags:
                tag_key = f"tag:{tag}"
                pipe.sadd(tag_key, key)
                if ttl:
                    pipe.expire(tag_key, ttl)
            await pipe.execute()
        except Exception as e:
            logger.error(f"Cache set_with_tags error for key {key}: {e}")

    async def invalidate_by_tag(self, tag: str) -> None:
        """Invalidate all keys associated with a tag."""
        if not self.enabled or not self.redis:
            return
        try:
            tag_key = f"tag:{tag}"
            keys = await self.redis.smembers(tag_key)
            if keys:
                await self.redis.delete(*keys)
                await self.redis.delete(tag_key)
            logger.info(f"Invalidated cache by tag: {tag}")
        except Exception as e:
            logger.error(f"Cache invalidation by tag error for {tag}: {e}")

    # ===== Helper Functions =====

    def _encode_value(self, value: Any) -> str:
        """Serialize and optionally compress a value into a string safe for Redis."""
        serialized = json.dumps(value, default=str).encode("utf-8")
        if len(serialized) >= self._compression_threshold:
            compressed = zlib.compress(serialized)
            return "1|" + base64.b64encode(compressed).decode("ascii")
        return "0|" + serialized.decode("utf-8")

    def _decode_value(self, data: Any) -> Any:
        """Decode a value stored with `_encode_value`."""
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        if not isinstance(data, str):
            return data
        # Handle double-encoded strings (e.g., JSON-dumped value returned from fake Redis)
        if len(data) >= 2 and data[0] == '"' and data[-1] == '"':
            data = data[1:-1]
        if data.startswith("1|"):
            payload = base64.b64decode(data[2:])
            return json.loads(payload)
        if data.startswith("0|"):
            try:
                return json.loads(data[2:])
            except Exception:
                try:
                    coerced = data[2:].replace('\\"', '"')
                    return json.loads(coerced)
                except Exception:
                    pass
        # Fallback for legacy/plain storage
        try:
            return json.loads(data)
        except Exception:
            return None

    def _resolve_ttl(self, key: str, ttl: Optional[int]) -> int:
        if ttl is not None:
            return ttl
        for prefix, override in self.ttl_overrides.items():
            if key.startswith(prefix):
                return override
        return self.default_ttl

    def set_ttl_override(self, prefix: str, ttl: int) -> None:
        """Override default TTL for keys starting with prefix."""
        self.ttl_overrides[prefix] = ttl

    def _get_lock(self, key: str) -> asyncio.Lock:
        """Return an asyncio lock for a cache key to guard against stampedes."""
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def invalidate_nowait(self, pattern: str) -> None:
        """Fire-and-forget invalidation helper for sync code paths."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                asyncio.run(self.invalidate(pattern))
            except RuntimeError:
                pass
            return
        loop.create_task(self.invalidate(pattern))


def cache_key_user(prefix: str, user_id: int, **kwargs) -> str:
    """Generate cache key for user-specific data."""
    params = "_".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
    return f"{prefix}:user:{user_id}:{params}" if params else f"{prefix}:user:{user_id}"


def cache_key_list(prefix: str, **kwargs) -> str:
    """Generate cache key for list data."""
    params = "_".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
    return f"{prefix}:list:{params}" if params else f"{prefix}:list"


async def cached_query(cache_key: str, query_fn, ttl: int = 300, tags: list = None):
    """Cache helper for reusable query lambdas with optional tag invalidation."""
    # Try to get from cache
    cached_data = await cache_manager.get(cache_key)
    if cached_data is not None:
        logger.debug(f"Cache hit: {cache_key}")
        return cached_data

    # Execute query
    result = await query_fn() if asyncio.iscoroutinefunction(query_fn) else query_fn()

    # Store in cache
    if tags:
        await cache_manager.set_with_tags(cache_key, result, tags, ttl)
    else:
        await cache_manager.set(cache_key, result, ttl)

    return result


# Global cache instance
cache_manager = RedisCache()


def cache(
    prefix: str,
    ttl: int = 300,
    include_user: bool = False,
):
    """
    Decorator for caching endpoint responses.

    Args:
        prefix: Key prefix (e.g., "posts_list")
        ttl: Time to live in seconds
        include_user: If True, cache is unique per user
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if not cache_manager.enabled:
                return await func(*args, **kwargs)

            # Extract user ID if needed
            user_suffix = ""
            if include_user:
                # Try to find 'current_user' in kwargs
                user = kwargs.get("current_user")
                if user and hasattr(user, "id"):
                    user_suffix = f":u{user.id}"

            # Generate Cache Key
            # Simple, deterministic hash of non-request args to avoid leaks across users/services.
            params = {
                k: v
                for k, v in kwargs.items()
                if k
                not in ["request", "db", "background_tasks", "current_user", "service"]
            }
            param_str = hashlib.md5(
                json.dumps(params, sort_keys=True, default=str).encode()
            ).hexdigest()

            cache_key = f"{prefix}{user_suffix}:{param_str}"

            # Try to get from cache
            lock = cache_manager._get_lock(cache_key)
            async with lock:
                cached_data = await cache_manager.get(cache_key)
                if cached_data is not None:
                    logger.debug(f"Cache hit: {cache_key}")
                    return cached_data

                # Execute function
                result = await func(*args, **kwargs)

                # Function result might be a Pydantic model or list of models
                # We need to convert it to dict/json compatible format before caching
                # FastAPI handles Pydantic serialization automatically for response,
                # but for manual caching we rely on json.dumps default=str above.

                # Store in cache (Fire and forget set to avoid blocking)
                await cache_manager.set(cache_key, result, ttl)

                return result

        return wrapper

    return decorator


    # ===== Internal helpers =====

    def _encode_value(self, value: Any) -> str:
        """Serialize and optionally compress a value into a string safe for Redis."""
        serialized = json.dumps(value, default=str).encode("utf-8")
        if len(serialized) >= self._compression_threshold:
            compressed = zlib.compress(serialized)
            return "1|" + base64.b64encode(compressed).decode("ascii")
        return "0|" + serialized.decode("utf-8")

    def _decode_value(self, data: str) -> Any:
        """Decode a value stored with `_encode_value`."""
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        if not isinstance(data, str):
            return data
        if len(data) >= 2 and data[0] == '"' and data[-1] == '"':
            data = data[1:-1]
        if data.startswith("1|"):
            payload = base64.b64decode(data[2:])
            return json.loads(payload)
        if data.startswith("0|"):
            try:
                return json.loads(data[2:])
            except Exception:
                try:
                    coerced = data[2:].replace('\\"', '"')
                    return json.loads(coerced)
                except Exception:
                    pass
        # Fallback for legacy/plain storage
        try:
            return json.loads(data)
        except Exception:
            return None

    def _resolve_ttl(self, key: str, ttl: Optional[int]) -> int:
        if ttl is not None:
            return ttl
        for prefix, override in self.ttl_overrides.items():
            if key.startswith(prefix):
                return override
        return self.default_ttl

    def set_ttl_override(self, prefix: str, ttl: int) -> None:
        """Override default TTL for keys starting with prefix."""
        self.ttl_overrides[prefix] = ttl

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def invalidate_nowait(self, pattern: str) -> None:
        """Fire-and-forget invalidation helper for sync code paths."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                asyncio.run(self.invalidate(pattern))
            except RuntimeError:
                # Already in loop but not retrievable
                pass
            return
        loop.create_task(self.invalidate(pattern))
