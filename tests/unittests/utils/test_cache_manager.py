"""Tests for the CacheManager utility class."""

import threading

import pytest

from mxm_refdata.utils.cache_manager import CacheManager


@pytest.fixture
def cache():
    """Fixture to provide a fresh CacheManager instance for each test."""
    return CacheManager(maxsize=10)


def test_cache_set_and_get(cache):
    """Test basic set and get operations."""
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"


def test_cache_overwrite(cache):
    """Test overwriting an existing cache value."""
    cache.set("key1", "initial_value")
    cache.set("key1", "new_value")
    assert cache.get("key1") == "new_value"


def test_cache_invalidate(cache):
    """Test cache invalidation (removal of an item)."""
    cache.set("key1", "value1")
    cache.invalidate("key1")
    assert cache.get("key1") is None


def test_cache_clear(cache):
    """Test clearing the cache removes all items."""
    cache.set("key1", "value1")
    cache.set("key2", "value2")
    cache.clear()
    assert cache.get("key1") is None
    assert cache.get("key2") is None


def test_cache_eviction(cache):
    """Test LRU eviction when exceeding max size."""
    for i in range(11):  # maxsize is 10, so the first item should be evicted
        cache.set(f"key{i}", f"value{i}")

    assert cache.get("key0") is None  # Should be evicted
    assert cache.get("key10") == "value10"  # Latest entry should exist


def test_cache_thread_safety():
    """Test thread safety by performing concurrent cache operations."""
    cache = CacheManager(maxsize=1000)  # Increase cache size to avoid eviction

    def worker(thread_id):
        for i in range(100):
            cache.set(f"key-{thread_id}-{i}", f"value-{thread_id}-{i}")
            assert cache.get(f"key-{thread_id}-{i}") == f"value-{thread_id}-{i}"

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # Verify that some values exist after concurrent access
    assert cache.get("key-0-99") == "value-0-99", (
        "Cache did not store values correctly under concurrent access"
    )
