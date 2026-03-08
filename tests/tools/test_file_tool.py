"""Tests for low-level file tools."""

import pytest

from resume_agent.core.preview import PendingWriteManager
from resume_agent.tools.file_tool import FileWriteTool


@pytest.mark.asyncio
async def test_file_write_noop_when_content_is_unchanged(tmp_path):
    target = tmp_path / "resume.html"
    target.write_text("<html>ok</html>", encoding="utf-8")

    tool = FileWriteTool(workspace_dir=str(tmp_path))
    result = await tool.execute(path="resume.html", content="<html>ok</html>")

    assert result.success is True
    assert "No changes needed" in result.output
    assert result.data["changed"] is False
    assert result.data["no_op"] is True
    assert target.read_text(encoding="utf-8") == "<html>ok</html>"


@pytest.mark.asyncio
async def test_file_write_preview_mode_skips_pending_when_noop(tmp_path):
    target = tmp_path / "resume.html"
    target.write_text("<html>ok</html>", encoding="utf-8")

    tool = FileWriteTool(workspace_dir=str(tmp_path))
    preview = PendingWriteManager()
    tool._preview_manager = preview

    result = await tool.execute(path="resume.html", content="<html>ok</html>")

    assert result.success is True
    assert result.data["changed"] is False
    assert result.data["no_op"] is True
    assert preview.has_pending is False
