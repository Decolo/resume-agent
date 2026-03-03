"""CDP (Chrome DevTools Protocol) client for browser automation.

Connects to a Chrome instance via WebSocket and provides helpers for
navigation and content extraction. Can auto-launch Chrome if configured.

Chrome lifecycle (sync → kill stale debug instance → launch → poll) runs in
a blocking thread via ``asyncio.to_thread`` to avoid async/sync timing issues.

The user's personal Chrome is never touched. Only a previous debug Chrome
(identified by its ``--user-data-dir``) is killed when the profile is locked.

This is the system boundary — mock this class in tool tests.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import websockets

from resume_agent.tools.chrome_profile import sync_chrome_profile

logger = logging.getLogger(__name__)

_DEFAULT_PORT = 0  # 0 = auto-detect free port
_DEFAULT_PROFILE = "~/.resume-agent/chrome-profile"
_CDP_TIMEOUT = 30.0
_NAV_TIMEOUT = 30.0
_NAV_POLL = 2.0
_EXTRA_WAIT = 3.0

# Chrome binary paths by platform
_CHROME_PATHS = {
    "Darwin": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "Linux": "google-chrome",
    "Windows": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
}

_QUIT_TIMEOUT = 10  # seconds
_LOCK_RELEASE_WAIT = 2  # seconds after debug Chrome exits for lock file cleanup
_PORT_POLL_TIMEOUT = 30  # seconds
_PORT_POLL_INTERVAL = 0.3  # seconds


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _is_profile_locked(profile_dir: str) -> bool:
    """Check if Chrome's SingletonLock exists in the profile directory."""
    return (Path(profile_dir) / "SingletonLock").exists()


def _kill_debug_chrome(profile_dir: str) -> None:
    """Kill only the Chrome instance using the given --user-data-dir.

    Finds the process by matching ``--user-data-dir=<profile_dir>`` in the
    command line, sends SIGTERM, waits up to _QUIT_TIMEOUT seconds, then
    falls back to SIGKILL. Never touches the user's personal Chrome.
    """
    # Find PIDs whose cmdline contains our specific profile dir flag
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"--user-data-dir={profile_dir}"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        logger.warning("pgrep not found, cannot kill debug Chrome")
        return

    if result.returncode != 0 or not result.stdout.strip():
        logger.debug("No debug Chrome found for profile %s", profile_dir)
        return

    pids = [int(p) for p in result.stdout.strip().split("\n") if p.strip()]
    logger.info("Found debug Chrome PID(s) %s for profile %s", pids, profile_dir)

    # SIGTERM first
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    # Wait for exit
    deadline = time.monotonic() + _QUIT_TIMEOUT
    while time.monotonic() < deadline:
        alive = []
        for pid in pids:
            try:
                os.kill(pid, 0)  # probe — doesn't actually send a signal
                alive.append(pid)
            except ProcessLookupError:
                pass
        if not alive:
            break
        time.sleep(0.5)

    # SIGKILL stragglers
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    # Wait for lock file release
    logger.info("Waiting %ds for profile lock release...", _LOCK_RELEASE_WAIT)
    time.sleep(_LOCK_RELEASE_WAIT)


def _launch_chrome(port: int, profile_dir: str) -> subprocess.Popen:
    """Launch Chrome with debug port and anti-detection flags. Blocking."""
    chrome_bin = _CHROME_PATHS.get(platform.system())
    if not chrome_bin:
        raise RuntimeError(f"Unsupported platform: {platform.system()}")

    cmd = [
        chrome_bin,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--profile-directory=Default",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
    ]
    logger.info("Launching Chrome: %s", " ".join(cmd))
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def _wait_for_debug_port(port: int) -> None:
    """Poll GET /json/version until Chrome debug port is ready. Blocking."""
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + _PORT_POLL_TIMEOUT
    while time.monotonic() < deadline:
        try:
            req = urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2)
            if req.status == 200:
                logger.info("Debug port %d ready", port)
                return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(_PORT_POLL_INTERVAL)
    raise ConnectionError(f"Chrome debug port {port} not ready after {_PORT_POLL_TIMEOUT}s")


def _prepare_and_launch_chrome(profile_dir: str) -> int:
    """Sync profile → kill stale debug instance → pick port → launch → poll.

    Never touches the user's personal Chrome. Only kills a previous debug
    Chrome that holds the profile lock.

    Returns the debug port number.
    """
    sync_chrome_profile(profile_dir)

    port = _get_free_port()
    logger.info("Auto-detected free port: %d", port)

    if _is_profile_locked(profile_dir):
        logger.info("Profile locked — killing previous debug Chrome...")
        _kill_debug_chrome(profile_dir)

    _launch_chrome(port, profile_dir)
    _wait_for_debug_port(port)
    return port


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

    async def connect(self) -> None:
        """Connect to Chrome via CDP. Auto-launches Chrome if needed."""
        if self.port > 0:
            try:
                await self._connect_to_tab()
                return
            except (ConnectionError, httpx.ConnectError) as e:
                if not self.auto_launch:
                    raise ConnectionError(
                        f"Cannot connect to Chrome on port {self.port}. " "Start Chrome with remote debugging enabled."
                    ) from e

        if not self.auto_launch:
            raise ConnectionError("Cannot connect to Chrome. Start Chrome with remote debugging enabled.")

        # Run entire Chrome lifecycle in a blocking thread — no async/sync mixing
        self.port = await asyncio.to_thread(_prepare_and_launch_chrome, self.chrome_profile)
        await self._connect_to_tab()

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
            await asyncio.sleep(_NAV_POLL)

        if extra_wait > 0:
            await asyncio.sleep(extra_wait)

    async def extract_main_text(self) -> str:
        """Extract innerText of <main>, falling back to <body>."""
        return await self.evaluate("document.querySelector('main')?.innerText || document.body?.innerText || ''")

    async def get_ax_tree(self) -> List[dict]:
        """Get flattened accessibility tree nodes."""
        result = await self._send("Accessibility.getFullAXTree")
        return result.get("nodes", [])

    async def click_node_by_backend_id(self, backend_node_id: int) -> None:
        """Resolve a backend DOM node and click it via CDP."""
        resolve = await self._send("DOM.resolveNode", {"backendNodeId": backend_node_id})
        object_id = resolve["object"]["objectId"]
        await self._send(
            "Runtime.callFunctionOn",
            {
                "objectId": object_id,
                "functionDeclaration": """function() {
                    this.scrollIntoView({block: 'center'});
                    this.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
                    if (typeof this.click === 'function') this.click();
                }""",
            },
        )

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self._ws:
            if hasattr(self, "_receiver_task"):
                self._receiver_task.cancel()
            await self._ws.close()
            self._ws = None
