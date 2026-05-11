"""Tests for the CacheManager utility class."""

import threading

import pytest

from mxm.refdata.utils.cache_manager import CacheManager


@pytest.fixture
def cache() -> CacheManager[str]:
    """Fixture to provide a fresh CacheManager instance for each test."""
    return CacheManager[str](maxsize=10)


def test_cache_set_and_get(cache: CacheManager[str]) -> None:
    """Test basic set and get operations."""
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"


def test_cache_overwrite(cache: CacheManager[str]) -> None:
    cache.set("key1", "value1")
    cache.set("key1", "value2")
    assert cache.get("key1") == "value2"


def test_cache_invalidate(cache: CacheManager[str]) -> None:
    cache.set("key1", "value1")
    cache.invalidate("key1")
    assert cache.get("key1") is None


def test_cache_clear(cache: CacheManager[str]) -> None:
    cache.set("key1", "value1")
    cache.set("key2", "value2")
    cache.clear()
    assert cache.get("key1") is None
    assert cache.get("key2") is None


def test_lru_eviction(cache: CacheManager[str]) -> None:
    for i in range(11):
        cache.set(f"key{i}", f"value{i}")

    assert cache.get("key0") is None
    assert cache.get("key10") == "value10"


def test_cache_thread_safety() -> None:
    cache = CacheManager[str](maxsize=100)

    def worker(thread_id: int) -> None:
        for i in range(10):
            cache.set(f"{thread_id}:{i}", f"value-{thread_id}-{i}")

    threads = [
        threading.Thread(target=worker, args=(thread_id,)) for thread_id in range(10)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert cache.get("0:0") == "value-0-0"
