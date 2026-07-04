"""A cache manager for reference data."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TypeGuard, TypeVar, cast

from cachetools import LRUCache

V = TypeVar("V")
T = TypeVar("T")


class CacheManager[V]:
    """Thread-safe cache manager using an LRU cache."""

    def __init__(self, maxsize: int = 1000) -> None:
        self._cache: LRUCache[str, V] = LRUCache(maxsize=maxsize)
        self._lock = threading.Lock()

    def get(self, key: str) -> V | None:
        """Thread-safe retrieval from the cache."""
        with self._lock:
            return self._cache.get(key)

    def get_as(self, key: str, expected_type: type[T]) -> T | None:
        """Retrieve a cached value if it has the expected concrete type."""
        value = self.get(key)
        if isinstance(value, expected_type):
            return value
        return None

    def get_checked(
        self,
        key: str,
        guard: Callable[[object], TypeGuard[T]],
    ) -> T | None:
        """Retrieve a cached value if it passes a custom type guard."""
        value = self.get(key)
        if value is None:
            return None

        candidate = cast(object, value)
        if guard(candidate):
            return candidate

        return None

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
