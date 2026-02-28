"""CDP (Chrome DevTools Protocol) client for browser automation.

Connects to a Chrome instance via WebSocket and provides helpers for
navigation and content extraction. Can auto-launch Chrome if configured.

This is the system boundary — mock this class in tool tests.
"""

from __future__ import annotations

import asyncio
import json
import logging
import platform
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import websockets

logger = logging.getLogger(__name__)

_DEFAULT_PORT = 9222
_DEFAULT_PROFILE = "~/.resume-agent/chrome-profile"
_CDP_TIMEOUT = 30.0
_NAV_TIMEOUT = 15.0
_EXTRA_WAIT = 2.0
_LAUNCH_WAIT = 4.0  # seconds to wait after launching Chrome

# Chrome binary paths by platform
_CHROME_PATHS = {
    "Darwin": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "Linux": "google-chrome",
    "Windows": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
}


class CDPClient:
    """Async CDP client using websockets, with optional Chrome auto-launch."""

    def __init__(
        self,
        port: int = _DEFAULT_PORT,
        chrome_profile: str = _DEFAULT_PROFILE,
        auto_launch: bool = True,
    ):
        self.port = port
        self.chrome_profile = str(Path(chrome_profile).expanduser())
        self.auto_launch = auto_launch
        self._ws: Any = None
        self._msg_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._chrome_process: Optional[subprocess.Popen] = None

    async def connect(self) -> None:
        """Connect to Chrome via CDP. Auto-launches Chrome if needed."""
        try:
            await self._connect_to_tab()
        except (ConnectionError, httpx.ConnectError) as e:
            if not self.auto_launch:
                raise ConnectionError(
                    f"Cannot connect to Chrome on port {self.port}. " "Start Chrome with: ./poc/start-chrome.sh"
                ) from e

            logger.info("Chrome not running, auto-launching on port %d...", self.port)
            self._launch_chrome()
            await asyncio.sleep(_LAUNCH_WAIT)
            await self._connect_to_tab()

    def _launch_chrome(self) -> None:
        """Launch Chrome with remote debugging enabled."""
        chrome_bin = _CHROME_PATHS.get(platform.system())
        if not chrome_bin:
            raise RuntimeError(f"Unsupported platform: {platform.system()}")

        cmd = [
            chrome_bin,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.chrome_profile}",
        ]
        logger.info("Launching Chrome: %s", " ".join(cmd))
        self._chrome_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    async def _connect_to_tab(self) -> None:
        """Discover tabs and connect WebSocket to the first page tab."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://localhost:{self.port}/json")
            resp.raise_for_status()
            tabs = resp.json()

        tab = next((t for t in tabs if t.get("type") == "page"), tabs[0] if tabs else None)
        if not tab or "webSocketDebuggerUrl" not in tab:
            raise ConnectionError("No debuggable tab found.")

        ws_url = tab["webSocketDebuggerUrl"]
        logger.debug("Connecting to tab: %s", tab.get("title", tab.get("url", ws_url)))

        self._ws = await websockets.connect(ws_url)
        self._receiver_task = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self) -> None:
        """Background task to match CDP responses to pending requests."""
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending:
                    self._pending[msg_id].set_result(msg)
        except Exception:
            # Connection closed or error — resolve all pending with error
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("WebSocket closed"))

    async def _send(self, method: str, params: Optional[Dict] = None) -> Dict:
        """Send a CDP command and wait for response."""
        self._msg_id += 1
        msg_id = self._msg_id
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future

        await self._ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))

        try:
            result = await asyncio.wait_for(future, timeout=_CDP_TIMEOUT)
        finally:
            self._pending.pop(msg_id, None)

        if "error" in result:
            raise RuntimeError(f"CDP error [{method}]: {result['error'].get('message', result['error'])}")
        return result.get("result", {})

    async def evaluate(self, expression: str) -> Any:
        """Evaluate a JS expression in the page context."""
        result = await self._send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        if result.get("exceptionDetails"):
            exc = result["exceptionDetails"]
            text = exc.get("exception", {}).get("description") or exc.get("text", "Evaluation failed")
            raise RuntimeError(text)
        return result.get("result", {}).get("value")

    async def navigate(self, url: str, timeout: float = _NAV_TIMEOUT, extra_wait: float = _EXTRA_WAIT) -> None:
        """Navigate to URL and wait for page load."""
        await self._send("Page.navigate", {"url": url})
        await asyncio.sleep(1.0)

        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                ready = await self.evaluate("document.readyState")
                if ready == "complete":
                    break
            except Exception:
                pass
            await asyncio.sleep(0.5)

        if extra_wait > 0:
            await asyncio.sleep(extra_wait)

    async def extract_main_text(self) -> str:
        """Extract innerText of <main>, falling back to <body>."""
        return await self.evaluate("document.querySelector('main')?.innerText || document.body?.innerText || ''")

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self._ws:
            if hasattr(self, "_receiver_task"):
                self._receiver_task.cancel()
            await self._ws.close()
            self._ws = None
