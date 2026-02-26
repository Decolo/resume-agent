"""Web tools - fetch and read web page content (static HTML only).

Copied from the original core tools package and re-exported here so
the web-tools package is self-contained.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Tuple
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from resume_agent.core.tools.base import BaseTool, ToolResult

_ALLOWED_CONTENT_TYPES = (
    "text/",
    "application/json",
    "application/xml",
    "application/xhtml+xml",
)


class _HTMLTextExtractor(HTMLParser):
    """Extract visible text from HTML."""

    def __init__(self):
        super().__init__()
        self._skip = False
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag: str):
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data: str):
        if not self._skip:
            self._chunks.append(data)

    def get_text(self) -> str:
        return "".join(self._chunks)


class WebFetchTool(BaseTool):
    """Fetch raw content from a URL (static content only)."""

    name = "web_fetch"
    description = "Fetch raw content from a URL (static HTML/text/JSON only)."
    parameters = {
        "url": {
            "type": "string",
            "description": "URL to fetch (http/https only)",
            "required": True,
        },
        "timeout_seconds": {
            "type": "number",
            "description": "Request timeout in seconds (default: 10)",
            "default": 10,
        },
        "max_bytes": {
            "type": "integer",
            "description": "Maximum bytes to download (default: 2,000,000)",
            "default": 2000000,
        },
        "user_agent": {
            "type": "string",
            "description": "User-Agent header (default: resume-agent/1.0)",
            "default": "resume-agent/1.0",
        },
    }

    async def execute(
        self,
        url: str,
        timeout_seconds: float = 10,
        max_bytes: int = 2_000_000,
        user_agent: str = "resume-agent/1.0",
    ) -> ToolResult:
        try:
            content, content_type = self._fetch_url(
                url=url,
                timeout_seconds=timeout_seconds,
                max_bytes=max_bytes,
                user_agent=user_agent,
            )
            return ToolResult(
                success=True,
                output=content,
                data={
                    "url": url,
                    "content_type": content_type,
                    "bytes": len(content.encode("utf-8")),
                },
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _fetch_url(
        self,
        url: str,
        timeout_seconds: float,
        max_bytes: int,
        user_agent: str,
    ) -> Tuple[str, str]:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Only http/https URLs are supported.")

        req = Request(url, headers={"User-Agent": user_agent})
        with urlopen(req, timeout=timeout_seconds) as resp:
            content_type = (resp.headers.get("Content-Type") or "").lower()
            if content_type:
                if not content_type.startswith(_ALLOWED_CONTENT_TYPES):
                    raise ValueError(f"Unsupported content type: {content_type}")

            raw = resp.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise ValueError(f"Response too large (> {max_bytes} bytes).")

        charset_match = re.search(r"charset=([^\s;]+)", content_type)
        charset = charset_match.group(1) if charset_match else "utf-8"
        text = raw.decode(charset, errors="replace")
        return text, content_type


class WebReadTool(BaseTool):
    """Fetch a URL and return extracted readable text."""

    name = "web_read"
    description = "Fetch a URL and return extracted readable text (static content only)."
    parameters = {
        "url": {
            "type": "string",
            "description": "URL to fetch and read (http/https only)",
            "required": True,
        },
        "timeout_seconds": {
            "type": "number",
            "description": "Request timeout in seconds (default: 10)",
            "default": 10,
        },
        "max_bytes": {
            "type": "integer",
            "description": "Maximum bytes to download (default: 2,000,000)",
            "default": 2000000,
        },
        "max_chars": {
            "type": "integer",
            "description": "Maximum characters to return (default: 50,000)",
            "default": 50000,
        },
        "user_agent": {
            "type": "string",
            "description": "User-Agent header (default: resume-agent/1.0)",
            "default": "resume-agent/1.0",
        },
    }

    async def execute(
        self,
        url: str,
        timeout_seconds: float = 10,
        max_bytes: int = 2_000_000,
        max_chars: int = 50_000,
        user_agent: str = "resume-agent/1.0",
    ) -> ToolResult:
        try:
            fetcher = WebFetchTool()
            raw, content_type = fetcher._fetch_url(
                url=url,
                timeout_seconds=timeout_seconds,
                max_bytes=max_bytes,
                user_agent=user_agent,
            )

            text = raw
            if "html" in content_type:
                text = self._html_to_text(raw)

            cleaned = self._normalize_text(text)
            if len(cleaned) > max_chars:
                cleaned = cleaned[:max_chars]

            return ToolResult(
                success=True,
                output=cleaned,
                data={
                    "url": url,
                    "content_type": content_type,
                    "chars": len(cleaned),
                },
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _html_to_text(self, html: str) -> str:
        parser = _HTMLTextExtractor()
        parser.feed(html)
        return parser.get_text()

    def _normalize_text(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines()]
        lines = [line for line in lines if line]
        return "\n".join(lines)
