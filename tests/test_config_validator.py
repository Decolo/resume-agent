"""Tests for configuration validator."""

import os
import pytest
from unittest.mock import patch

from resume_agent.config_validator import (
    validate_config,
    has_errors,
    ConfigError,
    Severity,
    _resolve_api_key_value,
)


class TestValidateConfig:
    """Tests for validate_config()."""

    def _valid_config(self) -> dict:
        """Return a minimal valid config."""
        return {
            "api_key": "test-key-123",
            "model": "gemini-2.5-flash",
            "temperature": 0.7,
            "max_tokens": 4096,
        }

    @patch.dict(os.environ, {}, clear=True)
    def test_valid_config_no_errors(self):
        issues = validate_config(self._valid_config())
        assert not has_errors(issues)

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key(self):
        config = self._valid_config()
        config["api_key"] = ""
        issues = validate_config(config)
        assert has_errors(issues)
        api_errors = [e for e in issues if e.field == "api_key"]
        assert len(api_errors) == 1
        assert api_errors[0].severity == Severity.ERROR

    @patch.dict(os.environ, {"GEMINI_API_KEY": "env-key"}, clear=True)
    def test_env_var_overrides_missing_config_key(self):
        config = self._valid_config()
        config["api_key"] = "${GEMINI_API_KEY}"
        issues = validate_config(config)
        api_errors = [e for e in issues if e.field == "api_key"]
        assert len(api_errors) == 0

    @patch.dict(os.environ, {}, clear=True)
    def test_placeholder_without_env_var(self):
        config = self._valid_config()
        config["api_key"] = "${GEMINI_API_KEY}"
        issues = validate_config(config)
        assert has_errors(issues)

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_model(self):
        config = self._valid_config()
        config["model"] = ""
        issues = validate_config(config)
        model_errors = [e for e in issues if e.field == "model"]
        assert len(model_errors) == 1

    @patch.dict(os.environ, {}, clear=True)
    def test_temperature_out_of_range(self):
        config = self._valid_config()
        config["temperature"] = 3.0
        issues = validate_config(config)
        temp_errors = [e for e in issues if e.field == "temperature"]
        assert len(temp_errors) == 1

    @patch.dict(os.environ, {}, clear=True)
    def test_negative_temperature(self):
        config = self._valid_config()
        config["temperature"] = -1
        issues = validate_config(config)
        temp_errors = [e for e in issues if e.field == "temperature"]
        assert len(temp_errors) == 1

    @patch.dict(os.environ, {}, clear=True)
    def test_invalid_max_tokens(self):
        config = self._valid_config()
        config["max_tokens"] = 0
        issues = validate_config(config)
        token_errors = [e for e in issues if e.field == "max_tokens"]
        assert len(token_errors) == 1

    @patch.dict(os.environ, {}, clear=True)
    def test_invalid_multi_agent_enabled(self):
        config = self._valid_config()
        config["multi_agent"] = {"enabled": "maybe"}
        issues = validate_config(config)
        ma_errors = [e for e in issues if e.field == "multi_agent.enabled"]
        assert len(ma_errors) == 1

    @patch.dict(os.environ, {}, clear=True)
    def test_valid_multi_agent_auto(self):
        config = self._valid_config()
        config["multi_agent"] = {"enabled": "auto"}
        issues = validate_config(config)
        ma_errors = [e for e in issues if e.field == "multi_agent.enabled"]
        assert len(ma_errors) == 0

    @patch.dict(os.environ, {}, clear=True)
    def test_nonexistent_workspace_is_warning(self):
        config = self._valid_config()
        issues = validate_config(config, workspace_dir="/nonexistent/path/xyz")
        ws_issues = [e for e in issues if e.field == "workspace_dir"]
        assert len(ws_issues) == 1
        assert ws_issues[0].severity == Severity.WARNING

    @patch.dict(os.environ, {}, clear=True)
    def test_existing_workspace_no_warning(self, tmp_path):
        config = self._valid_config()
        issues = validate_config(config, workspace_dir=str(tmp_path))
        ws_issues = [e for e in issues if e.field == "workspace_dir"]
        assert len(ws_issues) == 0


class TestResolveApiKeyValue:
    """Tests for _resolve_api_key_value()."""

    @patch.dict(os.environ, {"GEMINI_API_KEY": "env-key"}, clear=True)
    def test_env_var_priority(self):
        assert _resolve_api_key_value("config-key") == "env-key"

    @patch.dict(os.environ, {}, clear=True)
    def test_config_key_fallback(self):
        assert _resolve_api_key_value("config-key") == "config-key"

    @patch.dict(os.environ, {}, clear=True)
    def test_empty_returns_empty(self):
        assert _resolve_api_key_value("") == ""

    @patch.dict(os.environ, {"MY_KEY": "resolved"}, clear=True)
    def test_placeholder_resolved(self):
        assert _resolve_api_key_value("${MY_KEY}") == "resolved"

    @patch.dict(os.environ, {}, clear=True)
    def test_placeholder_unresolved(self):
        assert _resolve_api_key_value("${MISSING_KEY}") == ""


class TestHasErrors:
    """Tests for has_errors()."""

    def test_empty_list(self):
        assert not has_errors([])

    def test_only_warnings(self):
        issues = [ConfigError("x", "msg", Severity.WARNING)]
        assert not has_errors(issues)

    def test_with_error(self):
        issues = [ConfigError("x", "msg", Severity.ERROR)]
        assert has_errors(issues)

    def test_mixed(self):
        issues = [
            ConfigError("x", "msg", Severity.WARNING),
            ConfigError("y", "msg", Severity.ERROR),
        ]
        assert has_errors(issues)
