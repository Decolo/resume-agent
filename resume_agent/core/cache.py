"""Caching layer for tool results to reduce redundant operations."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional


class CacheEntry:
    """A single cache entry with TTL (time-to-live)."""

    def __init__(self, value: Any, ttl_seconds: int = 300):
        """
        Initialize cache entry.

        Args:
            value: The cached value
            ttl_seconds: Time-to-live in seconds (default: 5 minutes)
        """
        self.value = value
        self.created_at = datetime.now()
        self.ttl = timedelta(seconds=ttl_seconds)
        self.hits = 0  # Track cache hits

    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        return datetime.now() - self.created_at > self.ttl

    def touch(self):
        """Record a cache hit."""
        self.hits += 1


class ToolCache:
    """
    Cache for tool execution results.

    Caches results based on tool name and arguments, with TTL expiration.
    """

    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._hits = 0
        self._misses = 0

    def _make_key(self, tool_name: str, args: Dict[str, Any]) -> str:
        """
        Create a deterministic cache key from tool name and arguments.

        Args:
            tool_name: Name of the tool
            args: Tool arguments

        Returns:
            SHA256 hash of the tool + args
        """
        # Create deterministic JSON representation
        data = json.dumps(
            {"tool": tool_name, "args": args},
            sort_keys=True,  # Ensure consistent ordering
            default=str,  # Handle non-serializable types
        )
        # Hash to create compact key
        return hashlib.sha256(data.encode()).hexdigest()

    def get(self, tool_name: str, args: Dict[str, Any]) -> Optional[Any]:
        """
        Get cached result if available and not expired.

        Args:
            tool_name: Name of the tool
            args: Tool arguments

        Returns:
            Cached value if found and valid, None otherwise
        """
        key = self._make_key(tool_name, args)
        entry = self._cache.get(key)

        if entry is None:
            self._misses += 1
            return None

        if entry.is_expired():
            # Remove expired entry
            del self._cache[key]
            self._misses += 1
            return None

        # Cache hit!
        entry.touch()
        self._hits += 1
        return entry.value

    def set(self, tool_name: str, args: Dict[str, Any], value: Any, ttl_seconds: int = 300):
        """
        Store a value in the cache.

        Args:
            tool_name: Name of the tool
            args: Tool arguments
            value: Value to cache
            ttl_seconds: Time-to-live in seconds (default: 5 minutes)
        """
        key = self._make_key(tool_name, args)
        self._cache[key] = CacheEntry(value, ttl_seconds)

    def clear(self):
        """Clear all cached entries."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def evict_expired(self):
        """Remove all expired entries from cache."""
        expired_keys = [key for key, entry in self._cache.items() if entry.is_expired()]
        for key in expired_keys:
            del self._cache[key]

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0.0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "total_requests": total_requests,
            "hit_rate": hit_rate,
            "cache_size": len(self._cache),
        }

    def print_stats(self):
        """Print cache statistics."""
        stats = self.get_stats()
        print("\n" + "=" * 60)
        print("CACHE STATISTICS")
        print("=" * 60)
        print(f"Cache Hits:       {stats['hits']}")
        print(f"Cache Misses:     {stats['misses']}")
        print(f"Hit Rate:         {stats['hit_rate']:.1%}")
        print(f"Cache Size:       {stats['cache_size']} entries")
        print("=" * 60 + "\n")


# Tool-specific cache configurations
CACHE_CONFIGS = {
    # Read-only tools - safe to cache
    "file_read": {"ttl": 60, "enabled": True},  # 1 minute
    "file_list": {"ttl": 30, "enabled": True},  # 30 seconds
    "resume_parse": {"ttl": 300, "enabled": True},  # 5 minutes
    "lint_resume": {"ttl": 120, "enabled": True},  # 2 minutes
    "job_match": {"ttl": 600, "enabled": True},  # 10 minutes
    # Write / validation tools - DO NOT cache
    "file_write": {"enabled": False},
    "bash": {"enabled": False},
    "resume_write": {"enabled": False},
    "resume_validate": {"enabled": False},  # Always re-validate (file may have changed)
}


def should_cache_tool(tool_name: str) -> bool:
    """
    Check if a tool should be cached.

    Args:
        tool_name: Name of the tool

    Returns:
        True if tool results should be cached
    """
    config = CACHE_CONFIGS.get(tool_name, {"enabled": False})
    return config.get("enabled", False)


def get_tool_ttl(tool_name: str) -> int:
    """
    Get TTL for a specific tool.

    Args:
        tool_name: Name of the tool

    Returns:
        TTL in seconds (default: 300)
    """
    config = CACHE_CONFIGS.get(tool_name, {"ttl": 300})
    return config.get("ttl", 300)
