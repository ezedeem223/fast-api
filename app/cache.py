from functools import wraps
from cachetools import TTLCache
import pickle

# A dictionary to hold separate caches for each decorated function.
# This allows each function to have its own TTL based on the provided expire parameter.
function_caches = {}


def cache(expire=300):
    """
    A decorator to cache the results of an async function using a TTLCache.

    Parameters:
    expire (int): Time-to-live for the cache in seconds.

    Returns:
    The decorated async function with caching.
    """

    def decorator(func):
        # Create a separate TTLCache for this function using the expire parameter.
        local_cache = TTLCache(maxsize=1000, ttl=expire)
        function_caches[func.__name__] = local_cache

        @wraps(func)
        async def wrapper(*args, **kwargs):
            """
            Wrapper function that checks for cached result before calling the async function.
            """
            # Create a unique key based on function name, arguments, and keyword arguments.
            key = pickle.dumps((func.__name__, args, kwargs))

            # If the key exists in the local cache, return the cached result.
            if key in local_cache:
                return local_cache[key]

            # Otherwise, execute the function and store the result in the cache.
            result = await func(*args, **kwargs)
            local_cache[key] = result
            return result

        return wrapper

    return decorator
