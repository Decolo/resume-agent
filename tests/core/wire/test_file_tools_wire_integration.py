"""Integration tests for real file tools through wire-mode agent loop."""

from __future__ import annotations

import asyncio

import pytest

from resume_agent.core.llm import LLMAgent, LLMConfig
from resume_agent.core.wire import QueueShutDown, Wire
from resume_agent.core.wire.types import ApprovalRequest, ToolResultEvent
from resume_agent.providers.types import FunctionCall, LLMResponse
from resume_agent.tools.file_tool import FileEditTool, FileWriteTool


class _ScriptedProvider:
    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self.generate_calls = 0

    async def generate(self, messages, tools, config):  # noqa: ANN001
        self.generate_calls += 1
        if self._responses:
            return self._responses.pop(0)
        return LLMResponse(text="done", function_calls=[])

    async def generate_stream(self, messages, tools, config):  # noqa: ANN001
        raise AssertionError("streaming path is not expected in this test")
        yield  # pragma: no cover


def _new_agent() -> LLMAgent:
    config = LLMConfig(api_key="test", provider="gemini", model="test-model")
    return LLMAgent(config=config, system_prompt="test")


def _register_real_tool(agent: LLMAgent, tool) -> None:  # noqa: ANN001
    params = {
        "properties": tool.parameters,
        "required": [k for k, v in tool.parameters.items() if v.get("required", False)],
    }
    mutation_fields = getattr(tool, "mutation_signature_fields", None)
    agent.register_tool(
        name=tool.name,
        description=tool.description,
        parameters=params,
        func=tool.execute,
        requires_approval=getattr(tool, "requires_approval", None),
        mutation_signature_fields=list(mutation_fields) if mutation_fields else None,
    )


async def _collect_from_ui(ui, timeout: float = 5.0) -> list:  # noqa: ANN001
    messages = []
    try:
        while True:
            msg = await asyncio.wait_for(ui.receive(), timeout=timeout)
            messages.append(msg)
    except (QueueShutDown, asyncio.TimeoutError):
        pass
    return messages


@pytest.mark.asyncio
async def test_file_write_append_mode_via_wire_integration(tmp_path):
    agent = _new_agent()
    write_tool = FileWriteTool(workspace_dir=str(tmp_path))
    _register_real_tool(agent, write_tool)

    agent.provider = _ScriptedProvider(
        [
            LLMResponse(
                text="",
                function_calls=[
                    FunctionCall(
                        name="file_write",
                        arguments={"path": "resume.md", "content": "line1\n", "mode": "overwrite"},
                        id="w1",
                    )
                ],
            ),
            LLMResponse(
                text="",
                function_calls=[
                    FunctionCall(
                        name="file_write",
                        arguments={"path": "resume.md", "content": "line2\n", "mode": "append"},
                        id="w2",
                    )
                ],
            ),
            LLMResponse(text="done", function_calls=[]),
        ]
    )

    wire = Wire()
    approver_ui = wire.ui_side()
    collector_ui = wire.ui_side()

    async def auto_approve():
        try:
            while True:
                msg = await approver_ui.receive()
                if isinstance(msg, ApprovalRequest):
                    msg.resolve("approve")
        except QueueShutDown:
            pass

    approve_task = asyncio.create_task(auto_approve())
    collector_task = asyncio.create_task(_collect_from_ui(collector_ui))
    response = await agent.run("append content", wire=wire)
    wire.shutdown()
    messages = await collector_task
    await approve_task

    assert response == "done"
    assert (tmp_path / "resume.md").read_text(encoding="utf-8") == "line1\nline2\n"

    approvals = [m for m in messages if isinstance(m, ApprovalRequest)]
    assert len(approvals) == 2
    tool_results = [m for m in messages if isinstance(m, ToolResultEvent)]
    assert len(tool_results) == 2
    assert all(m.success for m in tool_results)


@pytest.mark.asyncio
async def test_file_write_approval_context_comes_from_tool_layer(tmp_path):
    agent = _new_agent()
    write_tool = FileWriteTool(workspace_dir=str(tmp_path))
    _register_real_tool(agent, write_tool)

    target = tmp_path / "resume.md"
    target.write_text("before\n", encoding="utf-8")

    agent.provider = _ScriptedProvider(
        [
            LLMResponse(
                text="",
                function_calls=[
                    FunctionCall(
                        name="file_write",
                        arguments={"path": "resume.md", "content": "after\n", "mode": "overwrite"},
                        id="w-preview",
                    )
                ],
            ),
            LLMResponse(text="done", function_calls=[]),
        ]
    )

    wire = Wire()
    approver_ui = wire.ui_side()
    collector_ui = wire.ui_side()

    async def auto_approve():
        try:
            while True:
                msg = await approver_ui.receive()
                if isinstance(msg, ApprovalRequest):
                    msg.resolve("approve")
        except QueueShutDown:
            pass

    approve_task = asyncio.create_task(auto_approve())
    collector_task = asyncio.create_task(_collect_from_ui(collector_ui))
    response = await agent.run("overwrite file", wire=wire)
    wire.shutdown()
    messages = await collector_task
    await approve_task

    assert response == "done"
    approvals = [m for m in messages if isinstance(m, ApprovalRequest)]
    assert len(approvals) == 1
    assert "Diff preview for" in approvals[0].description
    assert "a/" in approvals[0].description and "b/" in approvals[0].description


@pytest.mark.asyncio
async def test_file_edit_single_replace_via_wire_integration(tmp_path):
    agent = _new_agent()
    edit_tool = FileEditTool(workspace_dir=str(tmp_path))
    _register_real_tool(agent, edit_tool)
    target = tmp_path / "resume.md"
    target.write_text("Title: Old\nBody\n", encoding="utf-8")

    agent.provider = _ScriptedProvider(
        [
            LLMResponse(
                text="",
                function_calls=[
                    FunctionCall(
                        name="file_edit",
                        arguments={
                            "path": "resume.md",
                            "old_string": "Title: Old",
                            "new_string": "Title: New",
                        },
                        id="e1",
                    )
                ],
            ),
            LLMResponse(text="updated", function_calls=[]),
        ]
    )

    wire = Wire()
    approver_ui = wire.ui_side()
    collector_ui = wire.ui_side()

    async def auto_approve():
        try:
            while True:
                msg = await approver_ui.receive()
                if isinstance(msg, ApprovalRequest):
                    msg.resolve("approve")
        except QueueShutDown:
            pass

    approve_task = asyncio.create_task(auto_approve())
    collector_task = asyncio.create_task(_collect_from_ui(collector_ui))
    response = await agent.run("edit title", wire=wire)
    wire.shutdown()
    messages = await collector_task
    await approve_task

    assert response == "updated"
    assert target.read_text(encoding="utf-8") == "Title: New\nBody\n"
    tool_results = [m for m in messages if isinstance(m, ToolResultEvent)]
    assert len(tool_results) == 1
    assert tool_results[0].success is True


@pytest.mark.asyncio
async def test_file_edit_ambiguous_single_replace_via_wire_integration(tmp_path):
    agent = _new_agent()
    edit_tool = FileEditTool(workspace_dir=str(tmp_path))
    _register_real_tool(agent, edit_tool)
    target = tmp_path / "resume.md"
    original = "A\nA\n"
    target.write_text(original, encoding="utf-8")

    agent.provider = _ScriptedProvider(
        [
            LLMResponse(
                text="",
                function_calls=[
                    FunctionCall(
                        name="file_edit",
                        arguments={"path": "resume.md", "old_string": "A", "new_string": "B"},
                        id="e2",
                    )
                ],
            ),
            LLMResponse(text="handled", function_calls=[]),
        ]
    )

    wire = Wire()
    approver_ui = wire.ui_side()
    collector_ui = wire.ui_side()

    async def auto_approve():
        try:
            while True:
                msg = await approver_ui.receive()
                if isinstance(msg, ApprovalRequest):
                    msg.resolve("approve")
        except QueueShutDown:
            pass

    approve_task = asyncio.create_task(auto_approve())
    collector_task = asyncio.create_task(_collect_from_ui(collector_ui))
    response = await agent.run("edit ambiguous", wire=wire)
    wire.shutdown()
    messages = await collector_task
    await approve_task

    assert response == "handled"
    assert target.read_text(encoding="utf-8") == original
    tool_results = [m for m in messages if isinstance(m, ToolResultEvent)]
    assert len(tool_results) == 1
    assert tool_results[0].success is False
    assert "matched 2 times" in tool_results[0].result


@pytest.mark.asyncio
async def test_file_edit_chinese_content_via_wire_integration(tmp_path):
    agent = _new_agent()
    edit_tool = FileEditTool(workspace_dir=str(tmp_path))
    _register_real_tool(agent, edit_tool)
    target = tmp_path / "resume.md"
    target.write_text("## 项目经验\n负责前端页面开发与性能优化。\n", encoding="utf-8")

    agent.provider = _ScriptedProvider(
        [
            LLMResponse(
                text="",
                function_calls=[
                    FunctionCall(
                        name="file_edit",
                        arguments={
                            "path": "resume.md",
                            "old_string": "负责前端页面开发与性能优化。",
                            "new_string": "负责前端架构设计、性能优化与工程化建设。",
                        },
                        id="e-zh",
                    )
                ],
            ),
            LLMResponse(text="updated", function_calls=[]),
        ]
    )

    wire = Wire()
    approver_ui = wire.ui_side()

    async def auto_approve():
        try:
            while True:
                msg = await approver_ui.receive()
                if isinstance(msg, ApprovalRequest):
                    msg.resolve("approve")
        except QueueShutDown:
            pass

    approve_task = asyncio.create_task(auto_approve())
    response = await agent.run("优化中文项目经验描述", wire=wire)
    wire.shutdown()
    await approve_task

    assert response == "updated"
    assert target.read_text(encoding="utf-8") == "## 项目经验\n负责前端架构设计、性能优化与工程化建设。\n"
