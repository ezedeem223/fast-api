"""Repository utility script."""
from redis.exceptions import ConnectionError, RedisError
print(issubclass(ConnectionError, RedisError))
