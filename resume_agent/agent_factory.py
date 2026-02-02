"""Agent factory for creating single-agent or multi-agent systems."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

from .agent import ResumeAgent, AgentConfig
from .llm import GeminiAgent, LLMConfig, load_config, load_raw_config
from .observability import AgentObserver
from .agents.registry import AgentRegistry
from .agents.delegation import DelegationManager, DelegationConfig
from .agents.history import MultiAgentHistoryManager, HistoryConfig
from .agents.parser_agent import ParserAgent
from .agents.writer_agent import WriterAgent
from .agents.formatter_agent import FormatterAgent
from .agents.orchestrator_agent import OrchestratorAgent
from .agents.base import AgentConfig as SpecializedAgentConfig
from .tools import (
    FileReadTool,
    FileWriteTool,
    FileListTool,
    FileRenameTool,
    BashTool,
    ResumeParserTool,
    ResumeWriterTool,
    WebFetchTool,
    WebReadTool,
)
from .skills.parser_prompt import PARSER_AGENT_PROMPT
from .skills.writer_prompt import WRITER_AGENT_PROMPT
from .skills.formatter_prompt import FORMATTER_AGENT_PROMPT
from .skills.orchestrator_prompt import ORCHESTRATOR_AGENT_PROMPT

logger = logging.getLogger(__name__)


@dataclass
class MultiAgentConfig:
    """Configuration for multi-agent system."""

    enabled: Any = False
    mode: str = "orchestrated"
    use_preview_models: bool = False
    preview_model: Optional[str] = None
    preview_orchestrator_model: Optional[str] = None

    # Per-agent configurations
    parser_config: Optional[Dict[str, Any]] = None
    writer_config: Optional[Dict[str, Any]] = None
    formatter_config: Optional[Dict[str, Any]] = None
    orchestrator_config: Optional[Dict[str, Any]] = None

    # Delegation configuration
    delegation_max_depth: int = 5
    delegation_timeout: float = 300.0
    enable_cycle_detection: bool = True

    # History configuration
    history_strategy: str = "isolated"
    max_messages_per_agent: int = 50
    max_tokens_per_agent: int = 100000


def load_multi_agent_config(config_data: Dict[str, Any]) -> MultiAgentConfig:
    """Load multi-agent configuration from config data.

    Args:
        config_data: Configuration dictionary

    Returns:
        MultiAgentConfig instance
    """
    ma_config = config_data.get("multi_agent", {})

    return MultiAgentConfig(
        enabled=ma_config.get("enabled", False),
        mode=ma_config.get("mode", "orchestrated"),
        use_preview_models=ma_config.get("use_preview_models", False),
        preview_model=ma_config.get("preview_model"),
        preview_orchestrator_model=ma_config.get("preview_orchestrator_model"),
        parser_config=ma_config.get("agents", {}).get("parser"),
        writer_config=ma_config.get("agents", {}).get("writer"),
        formatter_config=ma_config.get("agents", {}).get("formatter"),
        orchestrator_config=ma_config.get("agents", {}).get("orchestrator"),
        delegation_max_depth=ma_config.get("delegation", {}).get("max_depth", 5),
        delegation_timeout=ma_config.get("delegation", {}).get("timeout_seconds", 300.0),
        enable_cycle_detection=ma_config.get("delegation", {}).get("enable_cycle_detection", True),
        history_strategy=ma_config.get("history", {}).get("strategy", "isolated"),
        max_messages_per_agent=ma_config.get("history", {}).get("max_messages_per_agent", 50),
        max_tokens_per_agent=ma_config.get("history", {}).get("max_tokens_per_agent", 100000),
    )


def create_agent(
    llm_config: Optional[LLMConfig] = None,
    agent_config: Optional[AgentConfig] = None,
    workspace_dir: str = ".",
    session_manager: Optional[Any] = None,
) -> Union[ResumeAgent, OrchestratorAgent]:
    """Factory function to create the appropriate agent.

    If multi_agent.enabled is True in config, creates a multi-agent
    system with OrchestratorAgent. Otherwise, creates a single
    ResumeAgent for backward compatibility.

    Args:
        llm_config: LLM configuration (loaded from config if None)
        agent_config: Agent configuration
        workspace_dir: Workspace directory for tools
        session_manager: Optional session manager for persistence

    Returns:
        ResumeAgent or OrchestratorAgent depending on configuration
    """
    # Load raw configuration to access multi_agent section
    raw_config = load_raw_config()

    if llm_config is None:
        llm_config = load_config()

    # Check if multi-agent mode is enabled
    ma_config = load_multi_agent_config(raw_config)

    # Auto mode: route per request
    if isinstance(ma_config.enabled, str) and ma_config.enabled.lower() == "auto":
        logger.info("Creating auto-routing agent (single + multi)")
        single_agent = ResumeAgent(
            llm_config=llm_config,
            agent_config=agent_config or AgentConfig(workspace_dir=workspace_dir),
            session_manager=session_manager,
        )
        multi_agent = create_multi_agent_system(
            llm_config=llm_config,
            ma_config=ma_config,
            workspace_dir=workspace_dir,
            session_manager=session_manager,
        )
        return AutoAgent(single_agent=single_agent, multi_agent=multi_agent)

    if not ma_config.enabled:
        # Single-agent mode (backward compatible)
        logger.info("Creating single-agent ResumeAgent")
        return ResumeAgent(
            llm_config=llm_config,
            agent_config=agent_config or AgentConfig(workspace_dir=workspace_dir),
            session_manager=session_manager,
        )

    # Multi-agent mode
    logger.info("Creating multi-agent system with OrchestratorAgent")
    return create_multi_agent_system(
        llm_config=llm_config,
        ma_config=ma_config,
        workspace_dir=workspace_dir,
        session_manager=session_manager,
    )


class AutoAgent:
    """Route requests to single-agent or multi-agent based on intent."""

    def __init__(self, single_agent: ResumeAgent, multi_agent: OrchestratorAgent):
        self.single_agent = single_agent
        self.multi_agent = multi_agent
        # Expose agent for session management (defaults to single-agent)
        self.agent = single_agent.agent
        self.llm_agent = single_agent.agent

    def _should_use_multi(self, user_input: str) -> bool:
        text = (user_input or "").lower()
        # Prefer multi-agent for export/convert and multi-format requests
        format_markers = ["markdown", "md", "html", "json", "txt", "pdf", "docx"]
        format_hits = sum(1 for marker in format_markers if marker in text)
        if format_hits >= 2:
            return True
        if any(k in text for k in ["export", "convert", "format", "save as", "save to", "output"]):
            return True
        return False

    async def run(self, user_input: str) -> str:
        if self._should_use_multi(user_input):
            return await self.multi_agent.run(user_input)
        return await self.single_agent.run(user_input)

    async def chat(self, user_input: str) -> str:
        return await self.run(user_input)

    def reset(self) -> None:
        self.single_agent.reset()
        self.multi_agent.reset()


def create_multi_agent_system(
    llm_config: LLMConfig,
    ma_config: MultiAgentConfig,
    workspace_dir: str = ".",
    session_manager: Optional[Any] = None,
) -> OrchestratorAgent:
    """Create a complete multi-agent system.

    Args:
        llm_config: LLM configuration
        ma_config: Multi-agent configuration
        workspace_dir: Workspace directory for tools

    Returns:
        Configured OrchestratorAgent with all specialized agents
    """
    # Create shared components
    observer = AgentObserver()
    registry = AgentRegistry()

    # Create history manager
    history_config = HistoryConfig(
        strategy=ma_config.history_strategy,
        max_messages_per_agent=ma_config.max_messages_per_agent,
        max_tokens_per_agent=ma_config.max_tokens_per_agent,
    )
    history_manager = MultiAgentHistoryManager(config=history_config)

    # Create delegation manager
    delegation_config = DelegationConfig(
        max_depth=ma_config.delegation_max_depth,
        timeout_seconds=ma_config.delegation_timeout,
        enable_cycle_detection=ma_config.enable_cycle_detection,
    )
    delegation_manager = DelegationManager(
        registry=registry,
        observer=observer,
        config=delegation_config,
    )

    # Create tools
    tools = {
        "file_read": FileReadTool(workspace_dir),
        "file_write": FileWriteTool(workspace_dir),
        "file_list": FileListTool(workspace_dir),
        "file_rename": FileRenameTool(workspace_dir),
        "bash": BashTool(workspace_dir),
        "resume_parse": ResumeParserTool(workspace_dir),
        "resume_write": ResumeWriterTool(workspace_dir),
        "web_fetch": WebFetchTool(),
        "web_read": WebReadTool(),
    }

    # Create specialized agents
    parser_agent = _create_parser_agent(
        llm_config=llm_config,
        ma_config=ma_config,
        observer=observer,
        tools=tools,
        history_manager=history_manager,
        session_manager=session_manager,
    )
    registry.register(parser_agent)

    writer_agent = _create_writer_agent(
        llm_config=llm_config,
        ma_config=ma_config,
        observer=observer,
        tools=tools,
        history_manager=history_manager,
        session_manager=session_manager,
    )
    registry.register(writer_agent)

    formatter_agent = _create_formatter_agent(
        llm_config=llm_config,
        ma_config=ma_config,
        observer=observer,
        tools=tools,
        history_manager=history_manager,
        session_manager=session_manager,
    )
    registry.register(formatter_agent)

    # Create orchestrator
    orchestrator = _create_orchestrator_agent(
        llm_config=llm_config,
        ma_config=ma_config,
        observer=observer,
        tools=tools,
        history_manager=history_manager,
        registry=registry,
        delegation_manager=delegation_manager,
        session_manager=session_manager,
    )
    registry.register(orchestrator)

    # Register agent tools with orchestrator
    orchestrator.register_agent_tools()

    logger.info(
        f"Multi-agent system created with {len(registry)} agents: "
        f"{[a.agent_id for a in registry.get_all_agents()]}"
    )

    return orchestrator


def _create_parser_agent(
    llm_config: LLMConfig,
    ma_config: MultiAgentConfig,
    observer: AgentObserver,
    tools: Dict,
    history_manager: MultiAgentHistoryManager,
    session_manager: Optional[Any] = None,
) -> ParserAgent:
    """Create and configure ParserAgent."""
    # Get agent-specific config
    agent_config_data = ma_config.parser_config or {}
    model = agent_config_data.get("model", llm_config.model)
    if ma_config.use_preview_models and ma_config.preview_model:
        model = ma_config.preview_model

    agent_config = SpecializedAgentConfig(
        model=model,
        temperature=agent_config_data.get("temperature", 0.3),
        max_tokens=agent_config_data.get("max_tokens", llm_config.max_tokens),
        enabled=agent_config_data.get("enabled", True),
    )

    # Create LLM agent for parser
    llm_agent = GeminiAgent(
        config=LLMConfig(
            api_key=llm_config.api_key,
            model=agent_config.model,
            max_tokens=agent_config.max_tokens,
            temperature=agent_config.temperature,
            search_grounding=getattr(llm_config, "search_grounding", False),
        ),
        system_prompt=PARSER_AGENT_PROMPT,
        agent_id="parser_agent",
        session_manager=session_manager,
    )

    # Register parser-specific tools
    _register_tools(llm_agent, tools, ["resume_parse", "file_read", "file_list"])

    # Set history manager
    llm_agent.history_manager = history_manager.get_agent_history("parser_agent")

    return ParserAgent(
        config=agent_config,
        llm_agent=llm_agent,
        observer=observer,
    )


def _create_writer_agent(
    llm_config: LLMConfig,
    ma_config: MultiAgentConfig,
    observer: AgentObserver,
    tools: Dict,
    history_manager: MultiAgentHistoryManager,
    session_manager: Optional[Any] = None,
) -> WriterAgent:
    """Create and configure WriterAgent."""
    agent_config_data = ma_config.writer_config or {}
    model = agent_config_data.get("model", llm_config.model)
    if ma_config.use_preview_models and ma_config.preview_model:
        model = ma_config.preview_model

    agent_config = SpecializedAgentConfig(
        model=model,
        temperature=agent_config_data.get("temperature", 0.7),
        max_tokens=agent_config_data.get("max_tokens", llm_config.max_tokens),
        enabled=agent_config_data.get("enabled", True),
    )

    llm_agent = GeminiAgent(
        config=LLMConfig(
            api_key=llm_config.api_key,
            model=agent_config.model,
            max_tokens=agent_config.max_tokens,
            temperature=agent_config.temperature,
            search_grounding=getattr(llm_config, "search_grounding", False),
        ),
        system_prompt=WRITER_AGENT_PROMPT,
        agent_id="writer_agent",
        session_manager=session_manager,
    )

    _register_tools(llm_agent, tools, ["file_read", "file_write"])

    llm_agent.history_manager = history_manager.get_agent_history("writer_agent")

    return WriterAgent(
        config=agent_config,
        llm_agent=llm_agent,
        observer=observer,
    )


def _create_formatter_agent(
    llm_config: LLMConfig,
    ma_config: MultiAgentConfig,
    observer: AgentObserver,
    tools: Dict,
    history_manager: MultiAgentHistoryManager,
    session_manager: Optional[Any] = None,
) -> FormatterAgent:
    """Create and configure FormatterAgent."""
    agent_config_data = ma_config.formatter_config or {}
    model = agent_config_data.get("model", llm_config.model)
    if ma_config.use_preview_models and ma_config.preview_model:
        model = ma_config.preview_model

    agent_config = SpecializedAgentConfig(
        model=model,
        temperature=agent_config_data.get("temperature", 0.3),
        max_tokens=agent_config_data.get("max_tokens", llm_config.max_tokens),
        enabled=agent_config_data.get("enabled", True),
    )

    llm_agent = GeminiAgent(
        config=LLMConfig(
            api_key=llm_config.api_key,
            model=agent_config.model,
            max_tokens=agent_config.max_tokens,
            temperature=agent_config.temperature,
            search_grounding=getattr(llm_config, "search_grounding", False),
        ),
        system_prompt=FORMATTER_AGENT_PROMPT,
        agent_id="formatter_agent",
        session_manager=session_manager,
    )

    _register_tools(llm_agent, tools, ["resume_write", "file_read", "file_write"])

    llm_agent.history_manager = history_manager.get_agent_history("formatter_agent")

    return FormatterAgent(
        config=agent_config,
        llm_agent=llm_agent,
        observer=observer,
    )


def _create_orchestrator_agent(
    llm_config: LLMConfig,
    ma_config: MultiAgentConfig,
    observer: AgentObserver,
    tools: Dict,
    history_manager: MultiAgentHistoryManager,
    registry: AgentRegistry,
    delegation_manager: DelegationManager,
    session_manager: Optional[Any] = None,
) -> OrchestratorAgent:
    """Create and configure OrchestratorAgent."""
    agent_config_data = ma_config.orchestrator_config or {}
    model = agent_config_data.get("model", llm_config.model)
    if ma_config.use_preview_models:
        model = ma_config.preview_orchestrator_model or ma_config.preview_model or model

    agent_config = SpecializedAgentConfig(
        model=model,
        temperature=agent_config_data.get("temperature", 0.5),
        max_tokens=agent_config_data.get("max_tokens", llm_config.max_tokens),
        max_steps=agent_config_data.get("max_steps", 30),
        enabled=agent_config_data.get("enabled", True),
    )

    llm_agent = GeminiAgent(
        config=LLMConfig(
            api_key=llm_config.api_key,
            model=agent_config.model,
            max_tokens=agent_config.max_tokens,
            temperature=agent_config.temperature,
            search_grounding=getattr(llm_config, "search_grounding", False),
        ),
        system_prompt=ORCHESTRATOR_AGENT_PROMPT,
        agent_id="orchestrator_agent",
        session_manager=session_manager,
    )

    # Orchestrator gets file_list and bash tools
    _register_tools(llm_agent, tools, ["file_list", "file_rename", "web_read", "web_fetch"])

    llm_agent.history_manager = history_manager.get_master_history()

    orchestrator = OrchestratorAgent(
        config=agent_config,
        llm_agent=llm_agent,
        observer=observer,
        registry=registry,
        delegation_manager=delegation_manager,
    )

    # Set parent agent reference for auto-save
    if session_manager:
        llm_agent._parent_agent = orchestrator

    return orchestrator


def _register_tools(llm_agent: GeminiAgent, tools: Dict, tool_names: list) -> None:
    """Register specified tools with an LLM agent.

    Args:
        llm_agent: The LLM agent to register tools with
        tools: Dictionary of all available tools
        tool_names: List of tool names to register
    """
    for name in tool_names:
        if name not in tools:
            continue

        tool = tools[name]
        params = {
            "properties": tool.parameters,
            "required": [k for k, v in tool.parameters.items() if v.get("required", False)],
        }

        llm_agent.register_tool(
            name=tool.name,
            description=tool.description,
            parameters=params,
            func=tool.execute,
        )
