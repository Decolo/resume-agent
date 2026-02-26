"""Regression tests for LLM tool registry behavior."""

from resume_agent.core.llm import LLMAgent, LLMConfig


def test_get_tools_returns_tool_schema_not_registry_tuple():
    """_get_tools() should return ToolSchema objects."""
    agent = LLMAgent(
        LLMConfig(
            api_key="test-key",
            provider="kimi",
            model="kimi-k2-turbo-preview",
            api_base="https://api.moonshot.cn/v1",
        )
    )

    async def fake_tool(**kwargs):
        return kwargs

    agent.register_tool(
        name="file_read",
        description="Read file",
        parameters={"properties": {}, "required": []},
        func=fake_tool,
    )

    tools = agent._get_tools()

    assert tools is not None
    assert len(tools) == 1
    assert tools[0].name == "file_read"
