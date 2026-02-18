"""Resume Agent API app package."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .app import InMemoryRateLimiter, app, create_app, main

_EXPORTS = {"InMemoryRateLimiter", "app", "create_app", "main"}


def __getattr__(name: str) -> Any:
    if name in _EXPORTS:
        module = import_module(".app", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | _EXPORTS)


__all__ = ["InMemoryRateLimiter", "app", "create_app", "main"]
