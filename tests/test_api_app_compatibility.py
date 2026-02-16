"""Compatibility checks for Slice D API app extraction."""

from __future__ import annotations

from apps.api.resume_agent_api.app import (
    InMemoryRateLimiter as PackageInMemoryRateLimiter,
)
from apps.api.resume_agent_api.app import app as package_app
from apps.api.resume_agent_api.app import create_app as package_create_app
from apps.api.resume_agent_api.app import main as package_main
from resume_agent.web.app import InMemoryRateLimiter, app, create_app, main


def test_api_app_exports_are_compatible_with_new_source() -> None:
    assert app is package_app
    assert create_app is package_create_app
    assert main is package_main
    assert InMemoryRateLimiter is PackageInMemoryRateLimiter
