"""Preview mode — show diffs before writing files."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from resume_agent.tools.base import ToolResult


@dataclass
class PendingWrite:
    """A file write waiting for user approval."""

    path: str
    resolved_path: Path
    content: str
    original_content: Optional[str] = None  # None if new file


class PendingWriteManager:
    """Manages pending file writes in preview mode.

    When preview mode is on, file writes are intercepted and stored here
    instead of being written to disk. The user can then review diffs and
    approve or reject each write.
    """

    def __init__(self):
        self._pending: Dict[str, PendingWrite] = {}

    def add(self, path: str, content: str, resolved_path: Path) -> str:
        """Store a pending write and return a unified diff string.

        Args:
            path: The user-facing path (may be relative)
            content: The new content to write
            resolved_path: The absolute resolved path on disk

        Returns:
            Unified diff string showing the changes
        """
        original = None
        if resolved_path.exists() and resolved_path.is_file():
            try:
                original = resolved_path.read_text(encoding="utf-8")
            except Exception:
                original = None

        self._pending[path] = PendingWrite(
            path=path,
            resolved_path=resolved_path,
            content=content,
            original_content=original,
        )

        return self.get_diff(path)

    def get_diff(self, path: str) -> str:
        """Generate a unified diff for a pending write.

        Args:
            path: The path key

        Returns:
            Unified diff string, or full content if new file
        """
        pw = self._pending.get(path)
        if pw is None:
            return ""

        if pw.original_content is None:
            # New file — show full content as additions
            new_lines = pw.content.splitlines(keepends=True)
            diff_lines = difflib.unified_diff(
                [],
                new_lines,
                fromfile="/dev/null",
                tofile=path,
            )
            return "".join(diff_lines) or f"(new file: {len(pw.content)} characters)"

        old_lines = pw.original_content.splitlines(keepends=True)
        new_lines = pw.content.splitlines(keepends=True)
        diff_lines = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
        result = "".join(diff_lines)
        return result or "(no changes)"

    def approve(self, path: str) -> ToolResult:
        """Write a pending file to disk.

        Args:
            path: The path key to approve

        Returns:
            ToolResult indicating success or failure
        """
        pw = self._pending.pop(path, None)
        if pw is None:
            return ToolResult(success=False, output="", error=f"No pending write for: {path}")

        try:
            pw.resolved_path.parent.mkdir(parents=True, exist_ok=True)
            pw.resolved_path.write_text(pw.content, encoding="utf-8")
            return ToolResult(
                success=True,
                output=f"✓ Approved and wrote {len(pw.content)} characters to {path}",
                data={"path": path, "size": len(pw.content)},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def approve_all(self) -> List[ToolResult]:
        """Approve and write all pending files."""
        results = []
        for path in list(self._pending.keys()):
            results.append(self.approve(path))
        return results

    def reject(self, path: str) -> bool:
        """Discard a pending write. Returns True if found."""
        return self._pending.pop(path, None) is not None

    def reject_all(self) -> int:
        """Discard all pending writes. Returns count discarded."""
        count = len(self._pending)
        self._pending.clear()
        return count

    def list_pending(self) -> List[str]:
        """Return list of paths with pending writes."""
        return list(self._pending.keys())

    @property
    def has_pending(self) -> bool:
        return len(self._pending) > 0
