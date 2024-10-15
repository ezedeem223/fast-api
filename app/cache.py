from functools import wraps
from cachetools import TTLCache
import pickle

cache_storage = TTLCache(maxsize=1000, ttl=300)


def cache(expire=300):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = pickle.dumps((func.__name__, args, kwargs))

            if key in cache_storage:
                return cache_storage[key]

            result = await func(*args, **kwargs)
            cache_storage[key] = result
            return result

        return wrapper

    return decorator
