"""Compatibility wrapper for tool-result caching during monorepo migration."""

from __future__ import annotations

from packages.core.resume_agent_core.cache import CACHE_CONFIGS, CacheEntry, ToolCache, get_tool_ttl, should_cache_tool

__all__ = [
    "CACHE_CONFIGS",
    "CacheEntry",
    "ToolCache",
    "get_tool_ttl",
    "should_cache_tool",
]
