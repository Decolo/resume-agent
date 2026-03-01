"""Patchright client for browser automation.

This adapter mirrors the subset of CDPClient used by LinkedIn tools:
- connect
- navigate
- evaluate
- extract_main_text
- close

Patchright is Playwright-compatible and more resilient on anti-bot pages.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import subprocess
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

_NAV_TIMEOUT_SECONDS = 15.0
_EXTRA_WAIT_SECONDS = 2.0
_LAUNCH_WAIT_SECONDS = 4.0
_DEFAULT_CDP_PORT = 9222

logger = logging.getLogger(__name__)

# Chrome binary paths by platform (same convention as CDP client).
_CHROME_PATHS = {
    "Darwin": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "Linux": "google-chrome",
    "Windows": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
}


class PatchrightClient:
    """Async browser client powered by Patchright persistent context."""

    def __init__(
        self,
        chrome_profile: str,
        headless: bool = False,
        channel: Optional[str] = "chrome",
        executable_path: Optional[str] = None,
        cdp_endpoint: Optional[str] = None,
        auto_launch: bool = True,
    ):
        self.chrome_profile = str(Path(chrome_profile).expanduser())
        self.headless = headless
        self.channel = channel
        self.executable_path = str(Path(executable_path).expanduser()) if executable_path else None
        self.cdp_endpoint = cdp_endpoint
        self.auto_launch = auto_launch
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._chrome_process: Optional[subprocess.Popen] = None
        self._owns_page = False
        self._owns_context = False

    async def connect(self) -> None:
        """Start Patchright and open/reuse a persistent browser context."""
        try:
            from patchright.async_api import async_playwright  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError(
                "Patchright is not installed. Install with `uv pip install patchright` "
                "and run `uv run patchright install chromium`."
            ) from e

        self._playwright = await async_playwright().start()

        if self.cdp_endpoint:
            self._context = await self._connect_over_cdp_with_optional_launch()
            # CDP-attached mode can be shared by multiple tool calls.
            # Always create a dedicated page per client to avoid navigation races.
            self._page = await self._context.new_page()
            self._owns_page = True
        else:
            launch_kwargs: dict[str, Any] = {
                "user_data_dir": self.chrome_profile,
                "headless": self.headless,
                "args": [
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            }
            if self.channel:
                launch_kwargs["channel"] = self.channel
            if self.executable_path:
                launch_kwargs["executable_path"] = self.executable_path
            self._context = await self._playwright.chromium.launch_persistent_context(**launch_kwargs)
            self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
            self._owns_page = False
            self._owns_context = True

    async def _connect_over_cdp_with_optional_launch(self) -> Any:
        """Connect to a CDP endpoint, optionally auto-launching Chrome if missing."""
        try:
            browser = await self._playwright.chromium.connect_over_cdp(endpoint_url=self.cdp_endpoint)
        except Exception as e:
            if not self.auto_launch:
                raise ConnectionError(
                    f"Cannot connect to Chrome CDP endpoint {self.cdp_endpoint}. "
                    "Start Chrome with remote debugging or enable auto_launch."
                ) from e
            logger.info("CDP endpoint unavailable, auto-launching Chrome for Patchright attach...")
            self._launch_chrome_for_cdp()
            await asyncio.sleep(_LAUNCH_WAIT_SECONDS)
            browser = await self._playwright.chromium.connect_over_cdp(endpoint_url=self.cdp_endpoint)

        self._browser = browser
        if self._browser.contexts:
            self._owns_context = False
            return self._browser.contexts[0]
        self._owns_context = True
        return await self._browser.new_context()

    def _launch_chrome_for_cdp(self) -> None:
        """Launch local Chrome with remote debugging matching cdp_endpoint port."""
        parsed = urlparse(self.cdp_endpoint or "")
        port = parsed.port or _DEFAULT_CDP_PORT

        chrome_bin = self.executable_path or _CHROME_PATHS.get(platform.system())
        if not chrome_bin:
            raise RuntimeError(f"Unsupported platform: {platform.system()}")

        cmd = [
            chrome_bin,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={self.chrome_profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ]
        logger.info("Launching Chrome for Patchright CDP attach: %s", " ".join(cmd))
        self._chrome_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    async def navigate(
        self, url: str, timeout: float = _NAV_TIMEOUT_SECONDS, extra_wait: float = _EXTRA_WAIT_SECONDS
    ) -> None:
        """Navigate to URL and wait for page ready state."""
        if not self._page:
            raise RuntimeError("Patchright client not connected")

        await self.navigate_page(self._page, url, timeout=timeout, extra_wait=extra_wait)

    async def navigate_page(
        self, page: Any, url: str, timeout: float = _NAV_TIMEOUT_SECONDS, extra_wait: float = _EXTRA_WAIT_SECONDS
    ) -> None:
        """Navigate a specific page to URL and wait for page ready state."""
        if not page:
            raise RuntimeError("Patchright page is not available")
        await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            # Some pages keep long-polling; domcontentloaded is good enough in that case.
            pass
        if extra_wait > 0:
            await page.wait_for_timeout(int(extra_wait * 1000))

    async def evaluate(self, expression: str) -> Any:
        """Evaluate JS in page context."""
        if not self._page:
            raise RuntimeError("Patchright client not connected")
        return await self._page.evaluate(expression)

    async def extract_main_text(self) -> str:
        """Extract innerText of <main>, falling back to <body>."""
        value = await self.extract_main_text_page(self._page)
        return str(value) if value is not None else ""

    async def extract_main_text_page(self, page: Any) -> str:
        """Extract innerText of <main>, falling back to <body>, from a specific page."""
        if not page:
            raise RuntimeError("Patchright page is not available")
        value = await page.evaluate("document.querySelector('main')?.innerText || document.body?.innerText || ''")
        return str(value) if value is not None else ""

    async def new_page(self) -> Any:
        """Create a new page in the active context."""
        if not self._context:
            raise RuntimeError("Patchright context is not connected")
        return await self._context.new_page()

    async def close_page(self, page: Any) -> None:
        """Close a specific page."""
        if not page:
            return
        await page.close()

    async def click_first(self, selectors: list[str]) -> bool:
        """Click the first enabled element matching selectors."""
        if not self._page:
            raise RuntimeError("Patchright client not connected")

        for selector in selectors:
            locator = self._page.locator(selector)
            count = await locator.count()
            if count < 1:
                continue
            target = locator.first
            try:
                disabled_attr = await target.get_attribute("disabled")
                aria_disabled = await target.get_attribute("aria-disabled")
                css_class = (await target.get_attribute("class")) or ""
                if disabled_attr is not None or aria_disabled == "true" or "disabled" in css_class:
                    continue
                await target.scroll_into_view_if_needed()
                await target.click(timeout=2000)
                return True
            except Exception:
                continue
        return False

    async def close(self) -> None:
        """Close context and stop Patchright."""
        if self._page and self._owns_page:
            try:
                await self._page.close()
            except Exception:
                pass
        if self._context and self._owns_context:
            try:
                await self._context.close()
            except Exception:
                pass
        self._context = None
        self._page = None
        self._owns_page = False
        self._owns_context = False
        # For CDP-attached sessions, keep Chrome alive and only disconnect.
        if self._browser and not self.cdp_endpoint:
            try:
                await self._browser.close()
            except Exception:
                pass
        self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
