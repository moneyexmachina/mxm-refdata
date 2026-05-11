"""A cache manager for the reference data service."""

import threading

from cachetools import LRUCache


class CacheManager[V]:
    """Thread-safe cache manager using an LRU cache."""

    def __init__(self, maxsize: int = 1000) -> None:
        self._cache: LRUCache[str, V] = LRUCache(maxsize=maxsize)
        self._lock = threading.Lock()

    def get(self, key: str) -> V | None:
        """Thread-safe retrieval from the cache."""
        with self._lock:
            return self._cache.get(key)

    def set(self, key: str, value: V) -> None:
        """Thread-safe insertion into the cache."""
        with self._lock:
            self._cache[key] = value

    def invalidate(self, key: str) -> None:
        """Thread-safe removal from the cache."""
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        """Thread-safe clearing of the cache."""
        with self._lock:
            self._cache.clear()
