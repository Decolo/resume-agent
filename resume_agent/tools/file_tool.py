"""File operation tools - read, write, list, rename files."""

from pathlib import Path

from resume_agent.core.tools.base import BaseTool, ToolResult

# Constants
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


class FileReadTool(BaseTool):
    """Read contents of a file."""

    name = "file_read"
    description = "Read the contents of a file. Returns the file content as text."
    parameters = {
        "path": {
            "type": "string",
            "description": "Path to the file to read",
            "required": True,
        },
        "encoding": {
            "type": "string",
            "description": "File encoding (default: utf-8)",
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
    description = "Write content to a file. Creates parent directories if needed."
    parameters = {
        "path": {
            "type": "string",
            "description": "Path to the file to write",
            "required": True,
        },
        "content": {
            "type": "string",
            "description": "Content to write to the file",
            "required": True,
        },
        "encoding": {
            "type": "string",
            "description": "File encoding (default: utf-8)",
            "default": "utf-8",
        },
    }

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).resolve()
        self._preview_manager = None  # Set by CLI when preview mode is on

    async def execute(self, path: str, content: str, encoding: str = "utf-8") -> ToolResult:
        try:
            file_path = self._resolve_path(path)

            # Preview mode: intercept write, but return the same success
            # message as a real write so the LLM continues normally.
            if self._preview_manager is not None:
                self._preview_manager.add(path, content, file_path)
                return ToolResult(
                    success=True,
                    output=f"Successfully wrote {len(content)} characters to {path}",
                    data={"preview": True, "pending_path": path},
                )

            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding=encoding)
            return ToolResult(
                success=True,
                output=f"Successfully wrote {len(content)} characters to {path}",
                data={"path": str(file_path), "size": len(content)},
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
    description = "List files and directories in a given path."
    parameters = {
        "path": {
            "type": "string",
            "description": "Path to the directory to list (default: current directory)",
            "default": ".",
        },
        "pattern": {
            "type": "string",
            "description": "Glob pattern to filter files (e.g., '*.pdf')",
            "default": "*",
        },
        "recursive": {
            "type": "boolean",
            "description": "Whether to list recursively",
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


class FileRenameTool(BaseTool):
    """Rename (move) a file within the workspace."""

    name = "file_rename"
    description = "Rename or move a file to a new path within the workspace."
    parameters = {
        "source_path": {
            "type": "string",
            "description": "Current path of the file to rename",
            "required": True,
        },
        "dest_path": {
            "type": "string",
            "description": "New path for the file",
            "required": True,
        },
        "overwrite": {
            "type": "boolean",
            "description": "Overwrite destination if it exists (default: false)",
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
