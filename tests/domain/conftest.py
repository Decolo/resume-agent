"""Pytest configuration for domain package tests."""

import pytest


@pytest.fixture
def tmp_path_factory_wrapper(tmp_path_factory):
    """Wrapper for tmp_path_factory to ensure compatibility."""
    return tmp_path_factory
