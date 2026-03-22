"""Tests for configuration validator."""

import os
from unittest.mock import patch

from resume_agent.cli.config_validator import Severity, has_errors, validate_config


class TestValidateConfig:
    """Tests for validate_config()."""

    def _valid_config(self) -> dict:
        """Return a minimal valid config."""
        return {
            "api_key": "test-key-123",
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "temperature": 0.7,
            "max_tokens": 4096,
        }

    @patch.dict(os.environ, {}, clear=True)
    def test_validate_config_accepts_a_minimal_valid_config(self):
        issues = validate_config(self._valid_config())
        assert not has_errors(issues)

    @patch.dict(os.environ, {}, clear=True)
    def test_validate_config_reports_missing_api_key_as_an_error(self):
        config = self._valid_config()
        config["api_key"] = ""
        issues = validate_config(config)
        assert has_errors(issues)
        api_errors = [e for e in issues if e.field == "api_key"]
        assert len(api_errors) == 1
        assert api_errors[0].severity == Severity.ERROR

    @patch.dict(os.environ, {"GEMINI_API_KEY": "env-key"}, clear=True)
    def test_validate_config_accepts_placeholder_api_key_when_provider_env_var_is_set(self):
        config = self._valid_config()
        config["api_key"] = "${GEMINI_API_KEY}"
        issues = validate_config(config)
        api_errors = [e for e in issues if e.field == "api_key"]
        assert len(api_errors) == 0

    @patch.dict(os.environ, {}, clear=True)
    def test_validate_config_reports_unresolved_api_key_placeholder_as_an_error(self):
        config = self._valid_config()
        config["api_key"] = "${GEMINI_API_KEY}"
        issues = validate_config(config)
        assert has_errors(issues)

    @patch.dict(os.environ, {}, clear=True)
    def test_validate_config_reports_missing_model_as_an_error(self):
        config = self._valid_config()
        config["model"] = ""
        issues = validate_config(config)
        model_errors = [e for e in issues if e.field == "model"]
        assert len(model_errors) == 1

    @patch.dict(os.environ, {}, clear=True)
    def test_validate_config_reports_temperature_above_supported_range(self):
        config = self._valid_config()
        config["temperature"] = 3.0
        issues = validate_config(config)
        temp_errors = [e for e in issues if e.field == "temperature"]
        assert len(temp_errors) == 1

    @patch.dict(os.environ, {}, clear=True)
    def test_validate_config_reports_negative_temperature(self):
        config = self._valid_config()
        config["temperature"] = -1
        issues = validate_config(config)
        temp_errors = [e for e in issues if e.field == "temperature"]
        assert len(temp_errors) == 1

    @patch.dict(os.environ, {}, clear=True)
    def test_validate_config_reports_non_positive_max_tokens(self):
        config = self._valid_config()
        config["max_tokens"] = 0
        issues = validate_config(config)
        token_errors = [e for e in issues if e.field == "max_tokens"]
        assert len(token_errors) == 1

    @patch.dict(os.environ, {}, clear=True)
    def test_validate_config_reports_invalid_multi_agent_enabled_value(self):
        config = self._valid_config()
        config["multi_agent"] = {"enabled": "maybe"}
        issues = validate_config(config)
        ma_errors = [e for e in issues if e.field == "multi_agent.enabled"]
        assert len(ma_errors) == 1

    @patch.dict(os.environ, {}, clear=True)
    def test_validate_config_accepts_multi_agent_auto_mode(self):
        config = self._valid_config()
        config["multi_agent"] = {"enabled": "auto"}
        issues = validate_config(config)
        ma_errors = [e for e in issues if e.field == "multi_agent.enabled"]
        assert len(ma_errors) == 0

    @patch.dict(os.environ, {}, clear=True)
    def test_validate_config_warns_when_workspace_directory_does_not_exist(self):
        config = self._valid_config()
        issues = validate_config(config, workspace_dir="/nonexistent/path/xyz")
        ws_issues = [e for e in issues if e.field == "workspace_dir"]
        assert len(ws_issues) == 1
        assert ws_issues[0].severity == Severity.WARNING

    @patch.dict(os.environ, {}, clear=True)
    def test_validate_config_skips_workspace_warning_when_directory_exists(self, tmp_path):
        config = self._valid_config()
        issues = validate_config(config, workspace_dir=str(tmp_path))
        ws_issues = [e for e in issues if e.field == "workspace_dir"]
        assert len(ws_issues) == 0
