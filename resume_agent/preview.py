"""Compatibility wrapper for preview-mode pending writes during monorepo migration."""

from __future__ import annotations

from packages.core.resume_agent_core.preview import PendingWrite, PendingWriteManager

__all__ = ["PendingWrite", "PendingWriteManager"]
