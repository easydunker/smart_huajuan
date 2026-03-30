"""Local disk cache for retrieval results.

Provides TTL-based caching with JSON serialization for
OpenAlex and other retrieval results.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CacheEntry:
    """A single cache entry with metadata."""

    key: str
    data: Any
    timestamp: float
    ttl_seconds: int

    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        return time.time() > self.timestamp + self.ttl_seconds

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "key": self.key,
            "data": self.data,
            "timestamp": self.timestamp,
            "ttl_seconds": self.ttl_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CacheEntry":
        """Create CacheEntry from dictionary."""
        return cls(
            key=data["key"],
            data=data["data"],
            timestamp=data["timestamp"],
            ttl_seconds=data["ttl_seconds"],
        )


@dataclass
class CacheStats:
    """Statistics for cache operations."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total


class RetrievalCache:
    """Local disk cache for retrieval results.

    Provides TTL-based caching with JSON serialization.
    Cache entries are stored as individual JSON files.
    """

    DEFAULT_TTL_SECONDS = 86400  # 24 hours

    def __init__(
        self,
        cache_dir: Path,
        default_ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        """
        Initialize the retrieval cache.

        Args:
            cache_dir: Directory to store cache files.
            default_ttl_seconds: Default TTL for cache entries.
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.default_ttl_seconds = default_ttl_seconds
        self._stats = CacheStats()

    def _make_key(self, query: str) -> str:
        """Create a safe cache key from a query string.

        Args:
            query: The query string to hash.

        Returns:
            A safe filename-safe hash of the query.
        """
        # Use SHA256 for consistent hashing
        hash_obj = hashlib.sha256(query.encode("utf-8"))
        return hash_obj.hexdigest()

    def _get_cache_path(self, key: str) -> Path:
        """Get the file path for a cache key.

        Args:
            key: The cache key.

        Returns:
            Path to the cache file.
        """
        return self.cache_dir / f"{key}.json"

    def get(self, query: str) -> Any | None:
        """Get cached data for a query.

        Args:
            query: The query string.

        Returns:
            Cached data if found and not expired, None otherwise.
        """
        key = self._make_key(query)
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            self._stats.misses += 1
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                entry_data = json.load(f)

            entry = CacheEntry.from_dict(entry_data)

            if entry.is_expired():
                # Remove expired entry
                cache_path.unlink()
                self._stats.evictions += 1
                self._stats.misses += 1
                return None

            self._stats.hits += 1
            return entry.data

        except (json.JSONDecodeError, KeyError, OSError):
            # Corrupted cache file, remove it
            try:
                cache_path.unlink()
            except OSError:
                pass
            self._stats.misses += 1
            return None

    def set(
        self,
        query: str,
        data: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        """Cache data for a query.

        Args:
            query: The query string.
            data: The data to cache.
            ttl_seconds: Optional custom TTL for this entry.
        """
        key = self._make_key(query)
        cache_path = self._get_cache_path(key)

        entry = CacheEntry(
            key=key,
            data=data,
            timestamp=time.time(),
            ttl_seconds=ttl_seconds or self.default_ttl_seconds,
        )

        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(entry.to_dict(), f, ensure_ascii=False, indent=2)
        except OSError:
            # Failed to write cache, ignore
            pass

    def invalidate(self, query: str) -> bool:
        """Invalidate a cached entry.

        Args:
            query: The query string.

        Returns:
            True if an entry was removed, False otherwise.
        """
        key = self._make_key(query)
        cache_path = self._get_cache_path(key)

        if cache_path.exists():
            try:
                cache_path.unlink()
                return True
            except OSError:
                pass
        return False

    def clear(self) -> int:
        """Clear all cached entries.

        Returns:
            Number of entries removed.
        """
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
                count += 1
            except OSError:
                pass
        return count

    def get_stats(self) -> CacheStats:
        """Get cache statistics.

        Returns:
            CacheStats object with hit/miss statistics.
        """
        return CacheStats(
            hits=self._stats.hits,
            misses=self._stats.misses,
            evictions=self._stats.evictions,
        )
