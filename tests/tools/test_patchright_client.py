"""Tests for PatchrightClient resource ownership and cleanup behavior."""

from unittest.mock import AsyncMock

import pytest

from resume_agent.tools.patchright_client import PatchrightClient


@pytest.mark.asyncio
async def test_close_cdp_shared_context_does_not_close_context_or_browser():
    client = PatchrightClient(
        chrome_profile="/tmp/profile",
        cdp_endpoint="http://127.0.0.1:9222",
    )
    page = AsyncMock()
    context = AsyncMock()
    browser = AsyncMock()
    playwright = AsyncMock()

    client._page = page
    client._owns_page = True
    client._context = context
    client._owns_context = False
    client._browser = browser
    client._playwright = playwright

    await client.close()

    page.close.assert_awaited_once()
    context.close.assert_not_called()
    browser.close.assert_not_called()
    playwright.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_swallows_cleanup_exceptions():
    client = PatchrightClient(chrome_profile="/tmp/profile")
    client._context = AsyncMock()
    client._context.close.side_effect = RuntimeError("context close failed")
    client._owns_context = True
    client._browser = AsyncMock()
    client._browser.close.side_effect = RuntimeError("browser close failed")
    client._playwright = AsyncMock()
    client._playwright.stop.side_effect = RuntimeError("stop failed")

    # Should not raise even if cleanup operations fail.
    await client.close()


@pytest.mark.asyncio
async def test_connect_over_cdp_marks_owned_context_when_new_context_created():
    client = PatchrightClient(
        chrome_profile="/tmp/profile",
        cdp_endpoint="http://127.0.0.1:9222",
    )
    browser = AsyncMock()
    browser.contexts = []
    new_context = AsyncMock()
    browser.new_context = AsyncMock(return_value=new_context)
    chromium = AsyncMock()
    chromium.connect_over_cdp = AsyncMock(return_value=browser)
    client._playwright = AsyncMock()
    client._playwright.chromium = chromium

    context = await client._connect_over_cdp_with_optional_launch()

    assert context is new_context
    assert client._owns_context is True


@pytest.mark.asyncio
async def test_connect_over_cdp_uses_shared_context_when_available():
    client = PatchrightClient(
        chrome_profile="/tmp/profile",
        cdp_endpoint="http://127.0.0.1:9222",
    )
    shared_context = AsyncMock()
    browser = AsyncMock()
    browser.contexts = [shared_context]
    chromium = AsyncMock()
    chromium.connect_over_cdp = AsyncMock(return_value=browser)
    client._playwright = AsyncMock()
    client._playwright.chromium = chromium

    context = await client._connect_over_cdp_with_optional_launch()

    assert context is shared_context
    assert client._owns_context is False
