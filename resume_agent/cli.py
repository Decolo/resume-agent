"""Compatibility wrapper for CLI entrypoint during monorepo migration."""

from __future__ import annotations

from apps.cli.resume_agent_cli import app as _cli_app

main = _cli_app.main


def __getattr__(name: str):
    return getattr(_cli_app, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_cli_app)))


__all__ = ["main"]
