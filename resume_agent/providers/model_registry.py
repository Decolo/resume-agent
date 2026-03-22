"""Static model capability fallback registry for providers without metadata APIs."""

from __future__ import annotations

from typing import Dict, Optional

from .types import ModelCapabilities

# Conservative exact-match fallback registry. Keep this intentionally small and
# only populate models we are confident about. Users can override unknown models
# with `context_window_override` in config.
_OPENAI_COMPAT_MODEL_CAPABILITIES: Dict[str, Dict[str, Dict[str, int]]] = {
    "glm": {
        "glm-4.5-flash": {
            "context_window": 128_000,
            "max_output_tokens": 96_000,
        },
    },
}


def lookup_model_capabilities(provider: str, model: str) -> Optional[ModelCapabilities]:
    """Look up static fallback capability metadata for a provider/model pair."""
    provider_key = (provider or "").lower().strip()
    model_key = (model or "").strip()
    if not provider_key or not model_key:
        return None

    provider_models = _OPENAI_COMPAT_MODEL_CAPABILITIES.get(provider_key, {})
    data = provider_models.get(model_key)
    if not data:
        return None

    return ModelCapabilities(
        provider=provider_key,
        model=model_key,
        context_window=int(data["context_window"]),
        max_output_tokens=int(data["max_output_tokens"]) if "max_output_tokens" in data else None,
        source="registry",
    )
