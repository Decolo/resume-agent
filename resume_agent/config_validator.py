"""Configuration validator for Resume Agent startup checks."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass
class ConfigError:
    """A single configuration issue."""
    field: str
    message: str
    severity: Severity


def validate_config(raw_config: Dict[str, Any], workspace_dir: str = ".") -> List[ConfigError]:
    """Validate raw configuration and return a list of issues.

    Args:
        raw_config: Raw config dict from YAML
        workspace_dir: Workspace directory to validate

    Returns:
        List of ConfigError (empty = valid)
    """
    errors: List[ConfigError] = []

    # --- API Key ---
    api_key = _resolve_api_key_value(raw_config.get("api_key", ""))
    if not api_key:
        errors.append(ConfigError(
            field="api_key",
            message="GEMINI_API_KEY not set. Set the env var or add api_key to config/config.local.yaml",
            severity=Severity.ERROR,
        ))

    # --- Model ---
    model = raw_config.get("model", "")
    if not model or not isinstance(model, str):
        errors.append(ConfigError(
            field="model",
            message="model must be a non-empty string",
            severity=Severity.ERROR,
        ))

    # --- Temperature ---
    temperature = raw_config.get("temperature", 0.7)
    if not isinstance(temperature, (int, float)) or temperature < 0 or temperature > 2:
        errors.append(ConfigError(
            field="temperature",
            message=f"temperature must be a number between 0 and 2, got {temperature}",
            severity=Severity.ERROR,
        ))

    # --- Max tokens ---
    max_tokens = raw_config.get("max_tokens", 4096)
    if not isinstance(max_tokens, int) or max_tokens <= 0:
        errors.append(ConfigError(
            field="max_tokens",
            message=f"max_tokens must be a positive integer, got {max_tokens}",
            severity=Severity.ERROR,
        ))

    # --- Multi-agent enabled ---
    ma = raw_config.get("multi_agent", {})
    if ma:
        enabled = ma.get("enabled", False)
        valid_enabled = {True, False, "auto"}
        if enabled not in valid_enabled:
            errors.append(ConfigError(
                field="multi_agent.enabled",
                message=f"multi_agent.enabled must be true, false, or \"auto\", got {enabled!r}",
                severity=Severity.ERROR,
            ))

    # --- Workspace ---
    ws = Path(workspace_dir)
    if not ws.exists():
        errors.append(ConfigError(
            field="workspace_dir",
            message=f"Workspace directory does not exist: {workspace_dir}",
            severity=Severity.WARNING,
        ))

    return errors


def _resolve_api_key_value(config_api_key: str) -> str:
    """Resolve API key from env or config value without side effects.

    Returns the resolved key string, or empty string if unresolvable.
    """
    # Env var takes priority
    env_key = os.environ.get("GEMINI_API_KEY", "")
    if env_key:
        return env_key

    if not config_api_key:
        return ""

    # Not a placeholder
    if not config_api_key.startswith("${"):
        return config_api_key

    # Resolve ${VAR_NAME} placeholder
    if config_api_key.endswith("}"):
        var_name = config_api_key[2:-1]
        return os.environ.get(var_name, "")

    return ""


def has_errors(issues: List[ConfigError]) -> bool:
    """Check if any issues are errors (not just warnings)."""
    return any(e.severity == Severity.ERROR for e in issues)
