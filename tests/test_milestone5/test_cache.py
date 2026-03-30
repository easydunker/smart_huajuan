"""Tests for retrieval cache module."""

import json
import tempfile
import time
from pathlib import Path

import pytest

from aat.retrieval.cache import CacheEntry, CacheStats, RetrievalCache


class TestCacheEntry:
    """Test CacheEntry dataclass."""

    def test_creation(self) -> None:
        """Test creating a cache entry."""
        entry = CacheEntry(
            key="test_key",
            data={"result": "test_data"},
            timestamp=time.time(),
            ttl_seconds=3600,
        )

        assert entry.key == "test_key"
        assert entry.data == {"result": "test_data"}
        assert entry.ttl_seconds == 3600

    def test_is_expired_false(self) -> None:
        """Test that non-expired entry returns False."""
        entry = CacheEntry(
            key="test",
            data={},
            timestamp=time.time(),  # Now
            ttl_seconds=3600,  # 1 hour
        )

        assert entry.is_expired() is False

    def test_is_expired_true(self) -> None:
        """Test that expired entry returns True."""
        entry = CacheEntry(
            key="test",
            data={},
            timestamp=time.time() - 7200,  # 2 hours ago
            ttl_seconds=3600,  # 1 hour TTL
        )

        assert entry.is_expired() is True

    def test_to_dict(self) -> None:
        """Test serialization to dict."""
        entry = CacheEntry(
            key="test_key",
            data={"nested": {"value": 123}},
            timestamp=1234567890.0,
            ttl_seconds=3600,
        )

        d = entry.to_dict()

        assert d["key"] == "test_key"
        assert d["data"] == {"nested": {"value": 123}}
        assert d["timestamp"] == 1234567890.0
        assert d["ttl_seconds"] == 3600

    def test_from_dict(self) -> None:
        """Test deserialization from dict."""
        data = {
            "key": "test_key",
            "data": {"value": 456},
            "timestamp": 9876543210.0,
            "ttl_seconds": 7200,
        }

        entry = CacheEntry.from_dict(data)

        assert entry.key == "test_key"
        assert entry.data == {"value": 456}
        assert entry.timestamp == 9876543210.0
        assert entry.ttl_seconds == 7200


class TestCacheStats:
    """Test CacheStats dataclass."""

    def test_creation(self) -> None:
        """Test creating cache stats."""
        stats = CacheStats(hits=10, misses=5, evictions=2)

        assert stats.hits == 10
        assert stats.misses == 5
        assert stats.evictions == 2

    def test_defaults(self) -> None:
        """Test default values."""
        stats = CacheStats()

        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0

    def test_hit_rate(self) -> None:
        """Test hit rate calculation."""
        stats = CacheStats(hits=75, misses=25, evictions=0)

        assert stats.hit_rate == 0.75

    def test_hit_rate_empty(self) -> None:
        """Test hit rate with no operations."""
        stats = CacheStats()

        assert stats.hit_rate == 0.0


class TestRetrievalCache:
    """Test RetrievalCache class."""

    @pytest.fixture
    def temp_cache_dir(self) -> Path:
        """Create a temporary cache directory."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_init_creates_directory(self, temp_cache_dir: Path) -> None:
        """Test that initialization creates cache directory."""
        cache_dir = temp_cache_dir / "new_cache"
        cache = RetrievalCache(cache_dir)

        assert cache.cache_dir.exists()
        assert cache.cache_dir == cache_dir

    def test_make_key_consistency(self, temp_cache_dir: Path) -> None:
        """Test that same query produces same key."""
        cache = RetrievalCache(temp_cache_dir)

        key1 = cache._make_key("test query")
        key2 = cache._make_key("test query")

        assert key1 == key2
        assert len(key1) == 64  # SHA256 hex length

    def test_make_key_uniqueness(self, temp_cache_dir: Path) -> None:
        """Test that different queries produce different keys."""
        cache = RetrievalCache(temp_cache_dir)

        key1 = cache._make_key("query one")
        key2 = cache._make_key("query two")

        assert key1 != key2

    def test_set_and_get(self, temp_cache_dir: Path) -> None:
        """Test basic set and get operations."""
        cache = RetrievalCache(temp_cache_dir)

        data = {"results": ["item1", "item2"], "total": 2}
        cache.set("my_query", data)

        retrieved = cache.get("my_query")
        assert retrieved == data

    def test_get_missing(self, temp_cache_dir: Path) -> None:
        """Test that get returns None for missing key."""
        cache = RetrievalCache(temp_cache_dir)

        result = cache.get("nonexistent_query")
        assert result is None

    def test_ttl_expiration(self, temp_cache_dir: Path) -> None:
        """Test that entries expire after TTL."""
        cache = RetrievalCache(temp_cache_dir, default_ttl_seconds=1)

        cache.set("expires_quickly", {"data": "test"})

        # Should exist immediately
        assert cache.get("expires_quickly") is not None

        # Wait for expiration
        time.sleep(1.5)

        # Should be expired now
        assert cache.get("expires_quickly") is None

    def test_custom_ttl(self, temp_cache_dir: Path) -> None:
        """Test custom TTL per entry."""
        cache = RetrievalCache(temp_cache_dir, default_ttl_seconds=3600)

        # Set with very short TTL
        cache.set("short_lived", {"data": "test"}, ttl_seconds=1)

        time.sleep(1.5)

        # Should be expired
        assert cache.get("short_lived") is None

    def test_invalidate(self, temp_cache_dir: Path) -> None:
        """Test invalidating a specific entry."""
        cache = RetrievalCache(temp_cache_dir)

        cache.set("to_invalidate", {"data": "test"})
        assert cache.get("to_invalidate") is not None

        removed = cache.invalidate("to_invalidate")
        assert removed is True
        assert cache.get("to_invalidate") is None

    def test_invalidate_missing(self, temp_cache_dir: Path) -> None:
        """Test invalidating a non-existent entry."""
        cache = RetrievalCache(temp_cache_dir)

        removed = cache.invalidate("nonexistent")
        assert removed is False

    def test_clear(self, temp_cache_dir: Path) -> None:
        """Test clearing all entries."""
        cache = RetrievalCache(temp_cache_dir)

        cache.set("entry1", {"data": 1})
        cache.set("entry2", {"data": 2})
        cache.set("entry3", {"data": 3})

        removed = cache.clear()
        assert removed == 3

        assert cache.get("entry1") is None
        assert cache.get("entry2") is None
        assert cache.get("entry3") is None

    def test_clear_empty(self, temp_cache_dir: Path) -> None:
        """Test clearing an empty cache."""
        cache = RetrievalCache(temp_cache_dir)

        removed = cache.clear()
        assert removed == 0

    def test_corrupted_cache_file(self, temp_cache_dir: Path) -> None:
        """Test handling of corrupted cache files."""
        cache = RetrievalCache(temp_cache_dir)

        # Create a corrupted JSON file
        key = cache._make_key("corrupted_query")
        cache_path = cache._get_cache_path(key)
        cache_path.write_text("not valid json {{[}")

        # Should handle gracefully and return None
        result = cache.get("corrupted_query")
        assert result is None

    def test_stats_tracking(self, temp_cache_dir: Path) -> None:
        """Test cache statistics tracking."""
        cache = RetrievalCache(temp_cache_dir)

        # Initial state
        stats = cache.get_stats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.hit_rate == 0.0

        # Miss
        cache.get("nonexistent")
        stats = cache.get_stats()
        assert stats.misses == 1
        assert stats.hits == 0

        # Hit
        cache.set("exists", {"data": "test"})
        cache.get("exists")
        stats = cache.get_stats()
        assert stats.hits == 1
        assert stats.misses == 1
        assert stats.hit_rate == 0.5

    def test_eviction_stats(self, temp_cache_dir: Path) -> None:
        """Test eviction statistics."""
        cache = RetrievalCache(temp_cache_dir, default_ttl_seconds=1)

        cache.set("expires", {"data": "test"})
        time.sleep(1.5)

        # Access to trigger eviction
        cache.get("expires")

        stats = cache.get_stats()
        assert stats.evictions == 1
