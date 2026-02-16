"""Compatibility providers namespace during monorepo migration."""

from __future__ import annotations

from packages.providers.resume_agent_providers import (
    PROVIDER_DEFAULTS,
    ChatProvider,
    GeminiProvider,
    OpenAICompatibleProvider,
    create_provider,
)

__all__ = [
    "ChatProvider",
    "GeminiProvider",
    "OpenAICompatibleProvider",
    "PROVIDER_DEFAULTS",
    "create_provider",
]
