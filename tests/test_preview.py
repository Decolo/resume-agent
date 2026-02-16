"""Tests for preview mode (PendingWriteManager + tool integration)."""

import pytest

from resume_agent.preview import PendingWriteManager


class TestPendingWriteManager:
    """Unit tests for PendingWriteManager."""

    def test_add_new_file(self, tmp_path):
        mgr = PendingWriteManager()
        diff = mgr.add("output.md", "# Hello\n", tmp_path / "output.md")
        assert mgr.has_pending
        assert "output.md" in mgr.list_pending()
        # New file diff should mention the path
        assert "output.md" in diff

    def test_add_existing_file(self, tmp_path):
        existing = tmp_path / "resume.md"
        existing.write_text("# Old\n", encoding="utf-8")

        mgr = PendingWriteManager()
        diff = mgr.add("resume.md", "# New\n", existing)
        assert "Old" in diff
        assert "New" in diff
        assert mgr.has_pending

    def test_add_no_changes(self, tmp_path):
        existing = tmp_path / "same.md"
        existing.write_text("# Same\n", encoding="utf-8")

        mgr = PendingWriteManager()
        diff = mgr.add("same.md", "# Same\n", existing)
        assert "(no changes)" in diff

    def test_get_diff_unknown_path(self):
        mgr = PendingWriteManager()
        assert mgr.get_diff("nonexistent") == ""

    def test_approve_writes_file(self, tmp_path):
        target = tmp_path / "out.txt"
        mgr = PendingWriteManager()
        mgr.add("out.txt", "content here", target)

        result = mgr.approve("out.txt")
        assert result.success
        assert target.read_text() == "content here"
        assert not mgr.has_pending

    def test_approve_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "sub" / "dir" / "file.md"
        mgr = PendingWriteManager()
        mgr.add("sub/dir/file.md", "nested", target)

        result = mgr.approve("sub/dir/file.md")
        assert result.success
        assert target.read_text() == "nested"

    def test_approve_unknown_path(self):
        mgr = PendingWriteManager()
        result = mgr.approve("nope")
        assert not result.success
        assert "nope" in result.error

    def test_approve_all(self, tmp_path):
        mgr = PendingWriteManager()
        mgr.add("a.txt", "aaa", tmp_path / "a.txt")
        mgr.add("b.txt", "bbb", tmp_path / "b.txt")

        results = mgr.approve_all()
        assert len(results) == 2
        assert all(r.success for r in results)
        assert (tmp_path / "a.txt").read_text() == "aaa"
        assert (tmp_path / "b.txt").read_text() == "bbb"
        assert not mgr.has_pending

    def test_reject_single(self, tmp_path):
        mgr = PendingWriteManager()
        mgr.add("x.txt", "data", tmp_path / "x.txt")
        assert mgr.reject("x.txt")
        assert not mgr.has_pending
        assert not (tmp_path / "x.txt").exists()

    def test_reject_unknown(self):
        mgr = PendingWriteManager()
        assert not mgr.reject("nope")

    def test_reject_all(self, tmp_path):
        mgr = PendingWriteManager()
        mgr.add("a.txt", "a", tmp_path / "a.txt")
        mgr.add("b.txt", "b", tmp_path / "b.txt")
        count = mgr.reject_all()
        assert count == 2
        assert not mgr.has_pending

    def test_list_pending(self, tmp_path):
        mgr = PendingWriteManager()
        assert mgr.list_pending() == []
        mgr.add("one.md", "1", tmp_path / "one.md")
        mgr.add("two.md", "2", tmp_path / "two.md")
        assert set(mgr.list_pending()) == {"one.md", "two.md"}

    def test_overwrite_pending(self, tmp_path):
        """Adding the same path twice replaces the pending write."""
        mgr = PendingWriteManager()
        mgr.add("f.txt", "first", tmp_path / "f.txt")
        mgr.add("f.txt", "second", tmp_path / "f.txt")
        assert len(mgr.list_pending()) == 1
        result = mgr.approve("f.txt")
        assert result.success
        assert (tmp_path / "f.txt").read_text() == "second"

    def test_has_pending_property(self, tmp_path):
        mgr = PendingWriteManager()
        assert not mgr.has_pending
        mgr.add("x", "y", tmp_path / "x")
        assert mgr.has_pending
        mgr.reject_all()
        assert not mgr.has_pending


class TestFileWriteToolPreview:
    """Integration: FileWriteTool with preview manager."""

    @pytest.fixture
    def write_tool(self, tmp_path):
        from resume_agent.tools.file_tool import FileWriteTool

        tool = FileWriteTool(workspace_dir=str(tmp_path))
        return tool

    @pytest.mark.asyncio
    async def test_preview_mode_returns_diff(self, write_tool, tmp_path):
        mgr = PendingWriteManager()
        write_tool._preview_manager = mgr

        result = await write_tool.execute(path="test.md", content="# Hello")
        assert result.success
        assert "Successfully wrote" in result.output
        assert result.data.get("preview") is True
        assert not (tmp_path / "test.md").exists()  # Not written yet

    @pytest.mark.asyncio
    async def test_preview_off_writes_directly(self, write_tool, tmp_path):
        # No preview manager set — writes directly
        result = await write_tool.execute(path="test.md", content="# Hello")
        assert result.success
        assert (tmp_path / "test.md").exists()
        assert (tmp_path / "test.md").read_text() == "# Hello"

    @pytest.mark.asyncio
    async def test_preview_then_approve(self, write_tool, tmp_path):
        mgr = PendingWriteManager()
        write_tool._preview_manager = mgr

        await write_tool.execute(path="out.md", content="# Resume")
        assert not (tmp_path / "out.md").exists()

        result = mgr.approve("out.md")
        assert result.success
        assert (tmp_path / "out.md").read_text() == "# Resume"


class TestResumeWriterToolPreview:
    """Integration: ResumeWriterTool with preview manager."""

    @pytest.fixture
    def writer_tool(self, tmp_path):
        from resume_agent.tools.resume_writer import ResumeWriterTool

        tool = ResumeWriterTool(workspace_dir=str(tmp_path))
        return tool

    @pytest.mark.asyncio
    async def test_preview_md(self, writer_tool, tmp_path):
        mgr = PendingWriteManager()
        writer_tool._preview_manager = mgr

        result = await writer_tool.execute(path="resume.md", content="# John Doe")
        assert result.success
        assert "Successfully wrote" in result.output
        assert not (tmp_path / "resume.md").exists()

    @pytest.mark.asyncio
    async def test_preview_html(self, writer_tool, tmp_path):
        mgr = PendingWriteManager()
        writer_tool._preview_manager = mgr

        result = await writer_tool.execute(path="resume.html", content="# John Doe")
        assert result.success
        assert result.data.get("preview") is True

    @pytest.mark.asyncio
    async def test_no_preview_writes_directly(self, writer_tool, tmp_path):
        result = await writer_tool.execute(path="resume.md", content="# Jane Doe")
        assert result.success
        assert (tmp_path / "resume.md").read_text() == "# Jane Doe"
