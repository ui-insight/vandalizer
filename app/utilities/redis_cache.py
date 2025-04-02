import hashlib
from typing import Any, Optional

from redis import Redis
from redis.commands.json.path import Path


class RedisCache:
    """Redis-based cache implementation based on langchain_redis."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        ttl: Optional[int] = None,
        prefix: Optional[str] = "redis",
        redis_client: Optional[Redis] = None,
    ) -> None:
        self.redis = redis_client or Redis.from_url(redis_url)
        self.ttl = ttl
        self.prefix = prefix

    def _key(self, prompt: str, llm_string: str) -> str:
        """Create a key for the cache."""
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
        llm_string_hash = hashlib.md5(llm_string.encode()).hexdigest()
        return f"{self.prefix}:{prompt_hash}:{llm_string_hash}"

    def lookup(self, prompt: str, llm_string: str) -> Optional[Any]:
        """Look up the result of a previous language model call in the Redis cache.

        This method checks if there's a cached result for the given prompt and language
        model combination.

        Args:
            prompt (str): The input prompt for which to look up the cached result.
            llm_string (str): A string representation of the language model and
                              its parameters.

        Returns:
            Any: The cached result if found, or None if not present in the cache.

        """
        key = self._key(prompt, llm_string)
        return self.redis.json().get(key)

    def update(self, prompt: str, llm_string: str, return_val: Any) -> None:
        """Update the cache with a new result for a given prompt and language model.

        This method stores a new result in the Redis cache for the specified prompt and
        language model combination.

        Args:
            prompt (str): The input prompt associated with the result.
            llm_string (str): A string representation of the language model
                              and its parameters.
            return_val (RETURN_VAL_TYPE): The result to be cached, typically a list
                                          containing a single Generation object.

        Returns:
            None

        """
        key = self._key(prompt, llm_string)
        self.redis.json().set(key, Path.root_path(), return_val)
        if self.ttl is not None:
            self.redis.expire(key, self.ttl)

    def clear(self, **kwargs: Any) -> None:
        """Clear all entries in the Redis cache that match the cache prefix.

        This method removes all cache entries that start with the specified prefix.

        Args:
            **kwargs: Additional keyword arguments. Currently not used, but included
                    for potential future extensions.

        Returns:
            None

        """
        cursor = 0
        pipe = self.redis.pipeline()
        while True:
            try:
                cursor, keys = self.redis.scan(
                    cursor,
                    match=f"{self.prefix}:*",
                    count=100,
                )  # type: ignore[misc]
                if keys:
                    pipe.delete(*keys)
                    pipe.execute()

                if cursor == 0:
                    break
            finally:
                pipe.reset()
