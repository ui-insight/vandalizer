import hashlib
import json
import os
from typing import Any, Optional

from dotenv import load_dotenv
from redis import Redis
from redis.commands.json.path import Path
from redis.exceptions import ResponseError

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")


class RedisCache:
    """Redis-based cache implementation based on langchain_redis."""

    def __init__(
        self,
        redis_url: str = f"redis://{REDIS_HOST}:6379/0",
        ttl: Optional[int] = None,
        prefix: Optional[str] = "redis",
        redis_client: Optional[Redis] = None,
    ) -> None:
        self.redis = redis_client or Redis.from_url(redis_url)
        self.ttl = ttl
        self.prefix = prefix
        self._use_json_api = True

    import hashlib

    def _key(self, prompt: str, llm_string: str) -> str:
        """Create a key for the cache."""
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        llm_string_hash = hashlib.sha256(llm_string.encode("utf-8")).hexdigest()
        return f"{self.prefix}:{prompt_hash}:{llm_string_hash}"

    @staticmethod
    def _json_command_missing(exc: Exception) -> bool:
        """Detect whether a RedisJSON command is unavailable."""
        return isinstance(exc, ResponseError) and "unknown command" in str(exc).lower()

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
        if self._use_json_api:
            try:
                return self.redis.json().get(key)
            except ResponseError as exc:
                if self._json_command_missing(exc):
                    self._use_json_api = False
                else:
                    raise

        raw_value = self.redis.get(key)
        if raw_value is None:
            return None
        if isinstance(raw_value, bytes):
            raw_value = raw_value.decode("utf-8")
        try:
            return json.loads(raw_value)
        except (TypeError, json.JSONDecodeError):
            return None

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
        if self._use_json_api:
            try:
                self.redis.json().set(key, Path.root_path(), return_val)
                if self.ttl is not None:
                    self.redis.expire(key, self.ttl)
                return
            except ResponseError as exc:
                if self._json_command_missing(exc):
                    self._use_json_api = False
                else:
                    raise

        serialized_value = json.dumps(return_val)
        self.redis.set(key, serialized_value)
        if self.ttl is not None:
            self.redis.expire(key, self.ttl)

    def clear(self) -> None:
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
