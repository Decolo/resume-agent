"""Tests for low-level file tools."""

import pytest

from resume_agent.core.preview import PendingWriteManager
from resume_agent.tools.file_tool import FileEditTool, FileWriteTool


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


@pytest.mark.asyncio
async def test_file_write_append_mode_appends_content(tmp_path):
    target = tmp_path / "resume.md"
    target.write_text("line1\n", encoding="utf-8")

    tool = FileWriteTool(workspace_dir=str(tmp_path))
    result = await tool.execute(path="resume.md", content="line2\n", mode="append")

    assert result.success is True
    assert result.data["changed"] is True
    assert result.data["mode"] == "append"
    assert result.data["appended_chars"] == len("line2\n")
    assert target.read_text(encoding="utf-8") == "line1\nline2\n"


@pytest.mark.asyncio
async def test_file_write_append_mode_noop_when_content_empty(tmp_path):
    target = tmp_path / "resume.md"
    target.write_text("line1\n", encoding="utf-8")

    tool = FileWriteTool(workspace_dir=str(tmp_path))
    result = await tool.execute(path="resume.md", content="", mode="append")

    assert result.success is True
    assert result.data["changed"] is False
    assert result.data["no_op"] is True
    assert target.read_text(encoding="utf-8") == "line1\n"


@pytest.mark.asyncio
async def test_file_edit_single_replace(tmp_path):
    target = tmp_path / "resume.md"
    target.write_text("Frontend Engineer\nBackend Engineer\n", encoding="utf-8")

    tool = FileEditTool(workspace_dir=str(tmp_path))
    result = await tool.execute(
        path="resume.md",
        old_string="Frontend Engineer",
        new_string="Senior Frontend Engineer",
    )

    assert result.success is True
    assert result.data["changed"] is True
    assert result.data["replacements"] == 1
    assert "Senior Frontend Engineer" in target.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_file_edit_rejects_ambiguous_single_replace(tmp_path):
    target = tmp_path / "resume.md"
    target.write_text("A\nA\n", encoding="utf-8")

    tool = FileEditTool(workspace_dir=str(tmp_path))
    result = await tool.execute(path="resume.md", old_string="A", new_string="B")

    assert result.success is False
    assert "matched 2 times" in (result.error or "")


@pytest.mark.asyncio
async def test_file_edit_replace_all(tmp_path):
    target = tmp_path / "resume.md"
    target.write_text("A\nA\nA\n", encoding="utf-8")

    tool = FileEditTool(workspace_dir=str(tmp_path))
    result = await tool.execute(
        path="resume.md",
        old_string="A",
        new_string="B",
        replace_all=True,
    )

    assert result.success is True
    assert result.data["replacements"] == 3
    assert target.read_text(encoding="utf-8") == "B\nB\nB\n"
