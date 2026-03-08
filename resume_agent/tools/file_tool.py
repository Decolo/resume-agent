"""File operation tools - read, write, list, rename files."""

import difflib
import hashlib
from pathlib import Path
from typing import Any

from resume_agent.core.tools.base import BaseTool, ToolResult

# Constants
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def _safe_read_text(file_path: Path, encoding: str = "utf-8") -> str:
    """Read file text best-effort for preview generation."""
    try:
        if file_path.exists() and file_path.is_file():
            return file_path.read_text(encoding=encoding)
    except Exception:
        pass
    return ""


def _format_unified_diff(
    path: Path,
    original: str,
    updated: str,
    *,
    max_lines: int = 120,
    max_chars: int = 12000,
) -> str:
    """Format a unified diff preview with safety truncation."""
    if original == updated:
        return f"Diff preview for {path}:\n(no changes)"

    diff_lines = list(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )
    if not diff_lines:
        return f"Diff preview for {path}:\n(no changes)"

    if len(diff_lines) > max_lines:
        diff_lines = diff_lines[:max_lines]
        diff_lines.append("... (diff truncated)")

    diff_text = "\n".join(diff_lines)
    if len(diff_text) > max_chars:
        diff_text = diff_text[:max_chars] + "\n... (diff truncated)"

    return f"Diff preview for {path}:\n{diff_text}"


class FileReadTool(BaseTool):
    """Read contents of a file."""

    name = "file_read"
    description = (
        "Use when you need plain-text content from one local file. "
        "Accepts absolute or workspace-relative paths, rejects directories/binary files/"
        "files larger than 10MB, and returns raw text."
    )
    parameters = {
        "path": {
            "type": "string",
            "description": "Absolute or workspace-relative path to an existing text file.",
            "required": True,
        },
        "encoding": {
            "type": "string",
            "description": "Text decoding used to read the file. Default: utf-8.",
            "default": "utf-8",
        },
    }

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).resolve()

    def _is_binary(self, file_path: Path) -> bool:
        """Check if a file is binary by reading first chunk."""
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(512)
            return b"\x00" in chunk
        except Exception:
            return False

    async def execute(self, path: str, encoding: str = "utf-8") -> ToolResult:
        try:
            file_path = self._resolve_path(path)
            if not file_path.exists():
                return ToolResult(success=False, output="", error=f"File not found: {path}")
            if not file_path.is_file():
                return ToolResult(success=False, output="", error=f"Not a file: {path}")

            # Check file size
            file_size = file_path.stat().st_size
            if file_size > MAX_FILE_SIZE:
                return ToolResult(
                    success=False, output="", error=f"File too large: {file_size} bytes (max {MAX_FILE_SIZE} bytes)"
                )

            # Check if binary file
            if self._is_binary(file_path):
                return ToolResult(success=False, output="", error=f"Cannot read binary file: {path}")

            content = file_path.read_text(encoding=encoding)
            return ToolResult(
                success=True,
                output=content,
                data={"path": str(file_path), "size": len(content)},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return self.workspace_dir / p


class FileWriteTool(BaseTool):
    """Write contents to a file."""

    name = "file_write"
    requires_approval = True
    mutation_signature_fields = ("path", "content", "mode")
    description = (
        "Use when you need to create or overwrite a text file. "
        "Creates parent directories automatically; in preview mode it stages a pending write "
        "instead of writing to disk immediately."
    )
    parameters = {
        "path": {
            "type": "string",
            "description": "Absolute or workspace-relative target file path.",
            "required": True,
        },
        "content": {
            "type": "string",
            "description": "Full text content to write (this replaces existing file content).",
            "required": True,
        },
        "mode": {
            "type": "string",
            "description": "Write mode: overwrite (replace full file) or append (append to end).",
            "default": "overwrite",
        },
        "encoding": {
            "type": "string",
            "description": "Text encoding used when writing the file. Default: utf-8.",
            "default": "utf-8",
        },
    }

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).resolve()
        self._preview_manager = None  # Set by CLI when preview mode is on

    def build_approval_context(
        self,
        path: str,
        content: str,
        mode: str = "overwrite",
        encoding: str = "utf-8",
        **_kwargs: Any,
    ) -> str:
        """Build approval-time diff preview for file writes."""
        if not isinstance(path, str) or not isinstance(content, str):
            return ""

        file_path = self._resolve_path(path)
        original = _safe_read_text(file_path, encoding=encoding)
        mode_normalized = (mode or "overwrite").strip().lower()
        if mode_normalized not in {"overwrite", "append"}:
            mode_normalized = "overwrite"
        updated = content if mode_normalized == "overwrite" else original + content
        return _format_unified_diff(file_path, original, updated)

    async def execute(
        self,
        path: str,
        content: str,
        mode: str = "overwrite",
        encoding: str = "utf-8",
    ) -> ToolResult:
        try:
            mode_normalized = (mode or "overwrite").strip().lower()
            if mode_normalized not in {"overwrite", "append"}:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Invalid mode: {mode}. Supported modes: overwrite, append.",
                )
            file_path = self._resolve_path(path)
            existing_text = ""
            if file_path.exists() and file_path.is_file():
                try:
                    existing_text = file_path.read_text(encoding=encoding)
                except Exception:
                    existing_text = ""

            existing_size = len(existing_text)
            new_text = content if mode_normalized == "overwrite" else existing_text + content
            fingerprint = hashlib.sha1(new_text.encode("utf-8", "ignore")).hexdigest()[:12]
            changed = existing_text != new_text

            # No-op for idempotent writes: do not rewrite unchanged content.
            if not changed:
                return ToolResult(
                    success=True,
                    output=f"No changes needed for {path}; file content is already up to date.",
                    data={
                        "path": str(file_path),
                        "size": existing_size,
                        "changed": False,
                        "no_op": True,
                        "fingerprint_after": fingerprint,
                        "mode": mode_normalized,
                        "appended_chars": len(content) if mode_normalized == "append" else 0,
                    },
                )

            # Preview mode: intercept write, but return the same success
            # message as a real write so the LLM continues normally.
            if self._preview_manager is not None:
                self._preview_manager.add(path, new_text, file_path)
                return ToolResult(
                    success=True,
                    output=f"Successfully wrote {len(new_text)} characters to {path}",
                    data={
                        "preview": True,
                        "pending_path": path,
                        "path": str(file_path),
                        "size": len(new_text),
                        "changed": changed,
                        "fingerprint_after": fingerprint,
                        "mode": mode_normalized,
                        "appended_chars": len(content) if mode_normalized == "append" else 0,
                    },
                )

            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(new_text, encoding=encoding)
            return ToolResult(
                success=True,
                output=f"Successfully wrote {len(new_text)} characters to {path}",
                data={
                    "path": str(file_path),
                    "size": len(new_text),
                    "changed": changed,
                    "fingerprint_after": fingerprint,
                    "mode": mode_normalized,
                    "appended_chars": len(content) if mode_normalized == "append" else 0,
                },
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return self.workspace_dir / p


class FileListTool(BaseTool):
    """List files in a directory."""

    name = "file_list"
    description = (
        "Use when you need directory discovery before read/write actions. "
        "Lists files/directories for a path and optional glob pattern, optionally recursive. "
        "Output lines are tab-separated as: type, size_bytes, relative_path."
    )
    parameters = {
        "path": {
            "type": "string",
            "description": "Directory to list. Absolute or workspace-relative. Default: current directory.",
            "default": ".",
        },
        "pattern": {
            "type": "string",
            "description": "Glob filter (for example '*.md' or '**/*.json' when recursive=true).",
            "default": "*",
        },
        "recursive": {
            "type": "boolean",
            "description": "If true, recurse into subdirectories.",
            "default": False,
        },
    }

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).resolve()

    async def execute(self, path: str = ".", pattern: str = "*", recursive: bool = False) -> ToolResult:
        try:
            dir_path = self._resolve_path(path)
            if not dir_path.exists():
                return ToolResult(success=False, output="", error=f"Directory not found: {path}")
            if not dir_path.is_dir():
                return ToolResult(success=False, output="", error=f"Not a directory: {path}")

            if recursive:
                files = list(dir_path.rglob(pattern))
            else:
                files = list(dir_path.glob(pattern))

            file_list = []
            for f in sorted(files):
                rel_path = f.relative_to(dir_path) if f.is_relative_to(dir_path) else f
                file_type = "dir" if f.is_dir() else "file"
                size = f.stat().st_size if f.is_file() else 0
                file_list.append(f"{file_type}\t{size}\t{rel_path}")

            output = "\n".join(file_list) if file_list else "(empty directory)"
            return ToolResult(
                success=True,
                output=output,
                data={"count": len(files), "path": str(dir_path)},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return self.workspace_dir / p


class FileEditTool(BaseTool):
    """Edit a file by replacing strings."""

    name = "file_edit"
    requires_approval = True
    mutation_signature_fields = ("path", "old_string", "new_string", "replace_all")
    description = (
        "Use when you need targeted in-place text edits in an existing file. "
        "Replaces one match by default, or all matches when replace_all=true."
    )
    parameters = {
        "path": {
            "type": "string",
            "description": "Absolute or workspace-relative file path to edit.",
            "required": True,
        },
        "old_string": {
            "type": "string",
            "description": "Text to find (supports multi-line).",
            "required": True,
        },
        "new_string": {
            "type": "string",
            "description": "Replacement text (supports multi-line).",
            "required": True,
        },
        "replace_all": {
            "type": "boolean",
            "description": "Replace all matches when true; otherwise replace one match.",
            "default": False,
        },
        "encoding": {
            "type": "string",
            "description": "Text encoding used when reading/writing the file. Default: utf-8.",
            "default": "utf-8",
        },
    }

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).resolve()
        self._preview_manager = None  # Set by CLI when preview mode is on

    def build_approval_context(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        encoding: str = "utf-8",
        **_kwargs: Any,
    ) -> str:
        """Build approval-time diff preview for file edits."""
        if (
            not isinstance(path, str)
            or not isinstance(old_string, str)
            or not isinstance(new_string, str)
            or not old_string
        ):
            return ""

        file_path = self._resolve_path(path)
        original = _safe_read_text(file_path, encoding=encoding)
        if not original and not (file_path.exists() and file_path.is_file()):
            return ""
        updated = (
            original.replace(old_string, new_string) if replace_all else original.replace(old_string, new_string, 1)
        )
        return _format_unified_diff(file_path, original, updated)

    async def execute(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        encoding: str = "utf-8",
    ) -> ToolResult:
        try:
            if not old_string:
                return ToolResult(success=False, output="", error="old_string cannot be empty.")

            file_path = self._resolve_path(path)
            if not file_path.exists():
                return ToolResult(success=False, output="", error=f"File not found: {path}")
            if not file_path.is_file():
                return ToolResult(success=False, output="", error=f"Not a file: {path}")

            original = file_path.read_text(encoding=encoding)
            match_count = original.count(old_string)
            if match_count == 0:
                return ToolResult(
                    success=False,
                    output="",
                    error="No replacements made: old_string was not found.",
                )
            if not replace_all and match_count > 1:
                return ToolResult(
                    success=False,
                    output="",
                    error=(
                        f"old_string matched {match_count} times. "
                        "Set replace_all=true or provide a more specific old_string."
                    ),
                )

            updated = (
                original.replace(old_string, new_string) if replace_all else original.replace(old_string, new_string, 1)
            )
            changed = updated != original
            if not changed:
                return ToolResult(
                    success=True,
                    output=f"No changes needed for {path}; file content is already up to date.",
                    data={
                        "path": str(file_path),
                        "size": len(original),
                        "changed": False,
                        "no_op": True,
                        "replacements": 0,
                    },
                )

            replacement_count = match_count if replace_all else 1
            fingerprint = hashlib.sha1(updated.encode("utf-8", "ignore")).hexdigest()[:12]

            if self._preview_manager is not None:
                self._preview_manager.add(path, updated, file_path)
                return ToolResult(
                    success=True,
                    output=f"Successfully edited {path} ({replacement_count} replacement(s)).",
                    data={
                        "preview": True,
                        "pending_path": path,
                        "path": str(file_path),
                        "size": len(updated),
                        "changed": True,
                        "replacements": replacement_count,
                        "replace_all": replace_all,
                        "fingerprint_after": fingerprint,
                    },
                )

            file_path.write_text(updated, encoding=encoding)
            return ToolResult(
                success=True,
                output=f"Successfully edited {path} ({replacement_count} replacement(s)).",
                data={
                    "path": str(file_path),
                    "size": len(updated),
                    "changed": True,
                    "replacements": replacement_count,
                    "replace_all": replace_all,
                    "fingerprint_after": fingerprint,
                },
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return self.workspace_dir / p


class FileRenameTool(BaseTool):
    """Rename (move) a file within the workspace."""

    name = "file_rename"
    requires_approval = True
    mutation_signature_fields = ("source_path", "dest_path", "overwrite")
    description = (
        "Use when you need to rename or move one file path to another. "
        "Fails if source is missing or destination exists unless overwrite=true."
    )
    parameters = {
        "source_path": {
            "type": "string",
            "description": "Current file path to move/rename (absolute or workspace-relative).",
            "required": True,
        },
        "dest_path": {
            "type": "string",
            "description": "Destination file path (absolute or workspace-relative).",
            "required": True,
        },
        "overwrite": {
            "type": "boolean",
            "description": "If true, replace an existing destination file. Default: false.",
            "default": False,
        },
    }

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).resolve()

    async def execute(self, source_path: str, dest_path: str, overwrite: bool = False) -> ToolResult:
        try:
            src = self._resolve_path(source_path)
            dst = self._resolve_path(dest_path)

            if not src.exists():
                return ToolResult(success=False, output="", error=f"Source file not found: {source_path}")
            if not src.is_file():
                return ToolResult(success=False, output="", error=f"Source is not a file: {source_path}")

            if dst.exists():
                if not overwrite:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Destination already exists: {dest_path}. Set overwrite=true to replace.",
                    )
                if dst.is_dir():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Destination is a directory: {dest_path}.",
                    )

            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)

            return ToolResult(
                success=True,
                output=f"Renamed {source_path} to {dest_path}",
                data={"source": str(src), "dest": str(dst)},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return self.workspace_dir / p
