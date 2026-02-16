"""Provider factory and defaults."""

from __future__ import annotations

import os
from typing import Any, Dict

from .base import ChatProvider
from .gemini import GeminiProvider
from .openai_compat import OpenAICompatibleProvider

PROVIDER_DEFAULTS: Dict[str, Dict[str, str]] = {
    "gemini": {"api_base": "", "env_key": "GEMINI_API_KEY"},
    "glm": {"api_base": "https://open.bigmodel.cn/api/paas/v4", "env_key": "GLM_API_KEY"},
    "kimi": {"api_base": "https://api.moonshot.cn/v1", "env_key": "KIMI_API_KEY"},
    "deepseek": {"api_base": "https://api.deepseek.com", "env_key": "DEEPSEEK_API_KEY"},
    "minimax": {"api_base": "https://api.minimax.chat/v1", "env_key": "MINIMAX_API_KEY"},
}


def create_provider(
    provider: str,
    api_key: str,
    model: str,
    api_base: str = "",
    **kwargs: Any,
) -> ChatProvider:
    provider_name = (provider or "gemini").lower()
    api_key = _resolve_api_key(provider_name, api_key)

    if provider_name == "gemini":
        return GeminiProvider(
            api_key=api_key,
            model=model,
            api_base=api_base,
            search_grounding=bool(kwargs.get("search_grounding", False)),
        )

    defaults = PROVIDER_DEFAULTS.get(provider_name, {})
    base = api_base or defaults.get("api_base", "")
    return OpenAICompatibleProvider(
        api_key=api_key,
        model=model,
        api_base=base,
    )


def _resolve_api_key(provider: str, api_key: str) -> str:
    defaults = PROVIDER_DEFAULTS.get(provider, {})
    env_key = defaults.get("env_key", "")

    if env_key:
        env_value = os.environ.get(env_key, "")
        if env_value:
            return env_value

    if api_key and not api_key.startswith("${"):
        return api_key

    if api_key.startswith("${") and api_key.endswith("}"):
        env_var = api_key[2:-1]
        resolved = os.environ.get(env_var, "")
        if resolved:
            return resolved

    if env_key:
        raise ValueError(f"{env_key} not set. Please set the env var or add api_key to config/config.local.yaml")

    raise ValueError("API key not set. Please set the env var or add api_key to config/config.local.yaml")


__all__ = [
    "ChatProvider",
    "GeminiProvider",
    "OpenAICompatibleProvider",
    "PROVIDER_DEFAULTS",
    "create_provider",
]
