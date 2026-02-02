# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Resume Agent is an AI-powered resume modification tool built using Google's Gemini API with function calling. It's a Python-based agent that can parse, analyze, and improve resumes across multiple formats (PDF, DOCX, Markdown, JSON, HTML).

## Development Commands

### Installation
```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"
```

### Running the Agent
```bash
# Interactive mode
uv run resume-agent

# Or with Python module
uv run python -m resume_agent.cli

# Single prompt mode (non-interactive)
uv run resume-agent --prompt "Analyze the resume in examples/sample_resumes/sample_resume.md"

# Specify workspace directory
uv run resume-agent --workspace /path/to/resumes

# Quiet mode (minimal output)
uv run resume-agent --quiet
```

### Testing
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_phase1_improvements.py -v

# Run specific test
uv run pytest tests/test_phase1_improvements.py::TestRetryLogic::test_retry_success_on_first_attempt -v

# Run multi-agent tests (Phase 2)
uv run pytest tests/test_multi_agent_core.py -v

# Run session persistence tests (Phase 3)
uv run pytest tests/test_session_persistence.py -v

# Run with coverage
uv run pytest --cov=resume_agent --cov-report=html
```

## Architecture

### System Modes

The agent supports two operational modes:

1. **Single-Agent Mode** (default, backward compatible):
   - `ResumeAgent` handles all tasks directly
   - Uses all 6 tools (file_read, file_write, file_list, bash, resume_parse, resume_write)
   - Simpler, suitable for straightforward resume tasks

2. **Multi-Agent Mode** (Phase 2, advanced):
   - `OrchestratorAgent` coordinates specialized agents
   - Agents can delegate tasks to each other
   - Supports complex workflows with agent coordination
   - Enable via `multi_agent.enabled: true` in config

### Core Components

1. **LLM Client (`llm.py`, `llm_openai.py`)**:
   - Uses Google GenAI SDK for Gemini by default
   - `OpenAIAgent` provides an OpenAI-compatible adapter (not wired by default)
   - **Phase 1 Enhancements**:
     - `HistoryManager`: Automatic conversation pruning (50 messages, 100k tokens)
     - Parallel tool execution via `asyncio.gather()`
     - Retry logic with exponential backoff (3 attempts, 1s base delay, 2x exponential)
     - Integrated observability logging
     - Tool result caching with per-tool TTL configuration
   - Manages conversation history as `types.Content` objects
   - Automatically executes tool calls in a loop until completion

2. **Reliability & Observability (`retry.py`, `observability.py`)**:
   - **Retry Logic** (`retry.py`):
     - `RetryConfig`: Configurable retry parameters
     - `retry_with_backoff()`: Async retry with exponential backoff + jitter
     - `TransientError` / `PermanentError`: Error classification
     - Prevents thundering herd with ±20% jitter
   - **Observability** (`observability.py`):
     - `AgentEvent`: Structured event logging (tool calls, LLM requests, errors, steps)
     - `AgentObserver`: Collects metrics, tracks cache hit rate, estimates costs
     - Session statistics: tokens, cost, duration, error count

3. **Caching Layer (`cache.py`)**:
   - `ToolCache`: In-memory cache with TTL expiration
   - `CacheEntry`: Individual cache entries with hit tracking
   - Per-tool configuration: file_read (60s), file_list (30s), resume_parse (300s)
   - Write tools (file_write, bash, resume_write) never cached
   - Deterministic key generation via SHA256 hash

4. **Session Persistence (`session.py`)** (Phase 3):
   - `SessionSerializer`: Convert agent state to/from JSON
   - `SessionManager`: Save/load/list/delete sessions
   - `SessionIndex`: Fast session lookup with metadata cache
   - **Features**:
     - Full conversation history preservation
     - Observability data (tool calls, LLM requests, costs)
     - Multi-agent state (delegation history, shared context)
     - Auto-save after tool execution (optional)
   - **Storage**: `workspace/sessions/` directory with JSON files
   - **CLI Commands**: `/save`, `/load`, `/sessions`, `/delete-session`, `/auto-save`

5. **Agent Loop (`agent.py`)**:
   - `ResumeAgent` orchestrates the conversation
   - Initializes and registers all tools with the Gemini agent
   - Tools are registered with their schemas and execution functions
   - Max steps default: 50 iterations

5. **Tools System (`tools/`)**:
   - All tools inherit from `BaseTool` abstract class
   - Tools return `ToolResult` objects with metadata:
     - success, output, error, data (base fields)
     - execution_time_ms, tokens_used, cached, retry_count (Phase 1 additions)
   - Tool execution can be sync or async (agent handles both)
   - **Security Enhancements**:
     - `file_read`: 10MB size limit + binary file detection
     - `bash`: Expanded blocklist (rm, dd, mkfs, sudo, curl, etc.) + dangerous pattern detection (;, &&, ||, |, `, $(, ${, >, >>, 2>, <)
     - `resume_parse`: mtime-based caching to avoid re-parsing unchanged files
   - Available tools:
     - `file_read`, `file_write`, `file_list`: Basic file operations
     - `bash`: Shell command execution
     - `resume_parse`: Parse PDF/DOCX/MD/JSON resumes (uses PyMuPDF, python-docx)
     - `resume_write`: Generate MD/TXT/JSON/HTML output

6. **System Prompt (`skills/resume_expert.py`)**:
   - Contains `RESUME_EXPERT_PROMPT` with resume writing expertise
   - Includes ATS optimization guidelines, action verbs, STAR method
   - Defines the agent's workflow and writing guidelines

7. **Multi-Agent System (`agents/`)** (Phase 2):
   - **Protocol** (`protocol.py`): `AgentTask` and `AgentResult` for inter-agent communication
   - **BaseAgent** (`base.py`): Abstract base class for all specialized agents
   - **AgentRegistry** (`registry.py`): Central registry for agent discovery and capability-based routing
   - **DelegationManager** (`delegation.py`): Manages agent-to-agent delegation with cycle detection
   - **SharedContext** (`context.py`): Context sharing across agents
   - **MultiAgentHistoryManager** (`history.py`): Isolated histories per agent
   - **Specialized Agents**:
     - `ParserAgent`: Resume parsing and analysis (uses resume_parse, file_read, file_list)
     - `WriterAgent`: Content generation and improvement (uses file_read, file_write)
     - `FormatterAgent`: Format conversion (uses resume_write, file_read, file_write)
     - `OrchestratorAgent`: Coordinates all agents, routes tasks, aggregates results
   - **AgentTool** (`agent_tool.py`): Wraps agents as tools for seamless delegation
   - **AgentFactory** (`agent_factory.py`): Factory pattern for creating single-agent or multi-agent systems

### Multi-Agent Architecture (Phase 2)

#### Agent Hierarchy
```
User (CLI)
    ↓
AgentFactory
    ├─→ Single-Agent Mode: ResumeAgent (existing)
    └─→ Multi-Agent Mode: OrchestratorAgent
            ├─→ ParserAgent (parsing & analysis)
            ├─→ WriterAgent (content generation)
            └─→ FormatterAgent (format conversion)
```

#### Key Design Patterns

1. **Agent-as-Tool Pattern**:
   - Agents are wrapped as tools using `AgentTool` class
   - Orchestrator calls agents via function calling interface
   - Seamless integration with existing tool system

2. **Isolated History Strategy**:
   - Each agent maintains separate `HistoryManager`
   - Context passed explicitly via `AgentTask.context`
   - Prevents context pollution, easier debugging
   - Orchestrator maintains master history

3. **Capability-Based Routing**:
   - Agents register capabilities (e.g., "resume_parse", "content_improve")
   - `AgentRegistry` routes tasks based on capability matching
   - Scoring algorithm: 50% capability match + 30% success rate + 20% load

4. **Cycle Detection**:
   - DFS-based cycle detection in delegation graph
   - Prevents infinite delegation loops
   - Max delegation depth: 5 levels (configurable)

5. **Delegation Protocol**:
   ```
   AgentTask (input):
     - task_id, task_type, description, parameters
     - context (shared data), parent_task_id
     - max_depth (decrements with each delegation)

   AgentResult (output):
     - task_id, agent_id, success, output
     - metadata, sub_results (from delegated tasks)
     - execution_time_ms, error
   ```

#### Workflow Examples

**Simple Delegation**:
```
User: "Analyze my resume"
  ↓
OrchestratorAgent
  ↓ (delegates to)
ParserAgent → resume_parse tool → returns structured data
  ↓
OrchestratorAgent → formats response
```

**Complex Multi-Step**:
```
User: "Improve my resume and convert to HTML"
  ↓
OrchestratorAgent (breaks into subtasks)
  ├─→ ParserAgent (parse current resume)
  ├─→ WriterAgent (improve content with parsed data)
  └─→ FormatterAgent (convert to HTML with improved content)
  ↓
OrchestratorAgent (aggregates results)
```

**Parallel Execution**:
```
User: "Export in MD, HTML, and JSON"
  ↓
OrchestratorAgent
  ├─→ FormatterAgent (MD) ─┐
  ├─→ FormatterAgent (HTML) ├─→ asyncio.gather()
  └─→ FormatterAgent (JSON) ─┘
  ↓
OrchestratorAgent (aggregates)
```

#### Safety Mechanisms

- **Cycle Detection**: DFS algorithm prevents infinite delegation loops
- **Max Depth**: Delegation depth limited to 5 levels
- **Timeout**: 300s timeout per delegation with graceful fallback
- **Agent Isolation**: Each agent has restricted tool access (least privilege)
- **Load Tracking**: Prevents overloading individual agents

### Key Architectural Details

- **Function Calling**: Uses Google GenAI SDK's native function calling (not OpenAI format)
  - Parameters are converted from OpenAI-style to Gemini `types.Schema` format
  - Function responses are wrapped in `types.Part.from_function_response()`
  - History is maintained as list of `types.Content` objects
  - **Parallel Execution**: Multiple independent function calls execute concurrently via `asyncio.gather()`
  - **Sequential Execution**: Dependent calls handled via while loop in agent.run()

- **Tool Registration**: Tools define parameters in OpenAI format, but `agent.py` converts them to Gemini format when registering with `GeminiAgent.register_tool()`

- **Async Execution**: The agent loop is fully async, and tools can be either sync or async (detected with `asyncio.iscoroutinefunction()`)

- **Retry Strategy**: LLM API calls wrapped with retry logic (3 attempts, exponential backoff)

- **History Management**: Automatic pruning prevents context overflow
  - Sliding window: keeps last 50 messages
  - Token-based: removes oldest messages if > 100k tokens
  - Token estimation: 1 token ≈ 4 characters

- **Configuration**:
  - Config loaded from `config/config.local.yaml` by default, with `config.yaml` as fallback
  - API key can be in config file or environment variable (`GEMINI_API_KEY`)
  - Supports `${ENV_VAR}` syntax in config for environment variable substitution

## Configuration

### API Setup

The agent uses Google Gemini by default. Edit `config/config.local.yaml`:

```yaml
api_key: "your-gemini-api-key"  # or ${GEMINI_API_KEY}
model: "gemini-2.5-flash"       # or gemini-2.0-flash, gemini-1.5-pro
max_tokens: 4096
temperature: 0.7
```

Environment variables:
- `GEMINI_API_KEY`: Gemini API key (primary)
- `OPENAI_API_KEY`: Used when explicitly wiring the OpenAI-compatible client

### Important Notes

- **OpenAI-compatible adapter**: `llm_openai.py` exists, but default config loading returns `LLMConfig` for Gemini. Use `OpenAIConfig` or add config wiring to switch providers.
- **Workspace Directory**: Agent operates within a workspace directory (default: current directory)
- **File Formats**: Resume parser supports PDF, DOCX, Markdown, TXT, JSON; writer supports MD, TXT, JSON, HTML

## File Structure

```
resume_agent/
├── agent.py              # ResumeAgent class (single-agent mode)
├── agent_factory.py      # Factory for single/multi-agent creation
├── llm.py                # GeminiAgent with function calling, HistoryManager
├── cli.py                # Interactive CLI with Rich/prompt-toolkit
├── retry.py              # Retry logic with exponential backoff + jitter
├── observability.py      # Structured logging and metrics (multi-agent aware)
├── cache.py              # Tool result caching with TTL
├── agents/               # Multi-agent system (Phase 2)
│   ├── __init__.py
│   ├── protocol.py       # AgentTask, AgentResult
│   ├── base.py           # BaseAgent abstract class
│   ├── registry.py       # AgentRegistry for agent discovery
│   ├── delegation.py     # DelegationManager with cycle detection
│   ├── context.py        # SharedContext for inter-agent data
│   ├── history.py        # MultiAgentHistoryManager
│   ├── agent_tool.py     # AgentTool wrapper
│   ├── parser_agent.py   # ParserAgent (parsing & analysis)
│   ├── writer_agent.py   # WriterAgent (content generation)
│   ├── formatter_agent.py # FormatterAgent (format conversion)
│   └── orchestrator_agent.py # OrchestratorAgent (coordination)
├── tools/
│   ├── base.py           # BaseTool abstract class, ToolResult
│   ├── file_tool.py      # File read/write/list (with size/binary checks)
│   ├── bash_tool.py      # Shell execution (with enhanced security)
│   ├── resume_parser.py  # Multi-format parsing (with mtime caching)
│   └── resume_writer.py  # Multi-format generation
└── skills/
    ├── resume_expert.py  # System prompt (single-agent)
    ├── parser_prompt.py  # ParserAgent system prompt
    ├── writer_prompt.py  # WriterAgent system prompt
    ├── formatter_prompt.py # FormatterAgent system prompt
    └── orchestrator_prompt.py # OrchestratorAgent system prompt

tests/
├── test_phase1_improvements.py   # Phase 1 tests
├── test_function_call_pairing.py # History manager pairing tests
└── test_multi_agent_core.py      # Multi-agent core tests
```

## CLI Commands

When running interactively:
- `/help` - Show help message
- `/reset` - Reset conversation history
- `/save [name]` - Save current session (optional custom name)
- `/load <session_id>` - Load a saved session
- `/sessions` - List all saved sessions
- `/delete-session <id>` - Delete a saved session
- `/auto-save [on|off]` - Toggle auto-save after tool execution
- `/quit` or `/exit` - Exit the agent
- `/files` - List files in workspace
- `/config` - Show current configuration
- `/export [target] [format] [verbose]` - Export conversation history
- `/agents` - Show agent statistics (multi-agent mode only)
- `/delegation-tree` - Show delegation tree for last task (multi-agent mode only)
- `/trace` - Show delegation trace (multi-agent mode only)

## Configuration

### Single-Agent vs Multi-Agent Mode

Edit `config/config.local.yaml` to toggle between modes:

```yaml
# Single-agent mode (default)
multi_agent:
  enabled: false

# Multi-agent mode (Phase 2)
multi_agent:
  enabled: true
  mode: "orchestrated"

  agents:
    parser:
      enabled: true
      model: "gemini-2.5-flash"
      temperature: 0.3  # Lower for deterministic parsing

    writer:
      enabled: true
      model: "gemini-2.5-flash"
      temperature: 0.7  # Higher for creative writing

    formatter:
      enabled: true
      model: "gemini-2.5-flash"
      temperature: 0.3

    orchestrator:
      enabled: true
      model: "gemini-2.5-flash"
      temperature: 0.5

  delegation:
    max_depth: 5
    timeout_seconds: 300
    enable_cycle_detection: true

  history:
    strategy: "isolated"  # Each agent has separate history
    max_messages_per_agent: 50
    max_tokens_per_agent: 100000
```

### API Setup

The agent uses Google Gemini by default. Edit `config/config.local.yaml`:

```yaml
api_key: "your-gemini-api-key"  # or ${GEMINI_API_KEY}
model: "gemini-2.5-flash"       # or gemini-2.0-flash, gemini-1.5-pro
max_tokens: 4096
temperature: 0.7
```

Environment variables:
- `GEMINI_API_KEY`: Gemini API key (primary)
- `OPENAI_API_KEY`: Fallback if Gemini not configured

## Development Workflow

### Adding a New Tool

1. Create tool class in `resume_agent/tools/` extending `BaseTool`
2. Implement `execute()` method (can be sync or async)
3. Define `name`, `description`, and `parameters` attributes
4. Register tool in `ResumeAgent._init_tools()` (single-agent) or specialized agent (multi-agent)
5. Add tests in `tests/`

### Adding a New Specialized Agent (Multi-Agent Mode)

1. Create agent class in `resume_agent/agents/` extending `BaseAgent`
2. Define `agent_id`, `agent_type`, and `capabilities`
3. Implement `execute(task)` and `can_handle(task)` methods
4. Create system prompt in `resume_agent/skills/`
5. Register agent in `agent_factory.py`
6. Add tests in `tests/test_multi_agent_core.py` or a new focused test file

### Debugging Multi-Agent Delegation

1. Enable verbose logging in config: `log_level: "DEBUG"`
2. Use `/delegation-tree` command to visualize delegation chains
3. Use `/agents` command to see agent statistics
4. Check `AgentObserver` logs for delegation events
5. Inspect individual agent histories via `MultiAgentHistoryManager`

### Important Implementation Notes

- **Function Calling Format**: Uses Google GenAI SDK native format, NOT OpenAI format
  - Parameters converted from OpenAI-style to Gemini `types.Schema`
  - Responses wrapped in `types.Part.from_function_response()`
  - History as list of `types.Content` objects

- **History Management**:
  - Single-agent: One `HistoryManager` for all interactions
  - Multi-agent: Isolated `HistoryManager` per agent + master history in orchestrator
  - Automatic pruning with pair-aware logic (preserves function call/response pairs)

- **Async Patterns**:
  - All agent loops are fully async
  - Tools can be sync or async (detected with `asyncio.iscoroutinefunction()`)
  - Parallel execution via `asyncio.gather()` for independent operations

- **Error Handling**:
  - Retry logic with exponential backoff (3 attempts, 1s base, 2x exponential)
  - Transient vs permanent error classification
  - Graceful degradation in multi-agent mode (fallback to orchestrator)

## Troubleshooting

See `docs/troubleshooting.md` for common issues including:
- Gemini API errors (function call pairing, rate limits)
- Installation issues (PyMuPDF, python-docx)
- File parsing issues (size limits, binary detection)
- Performance issues (caching, token usage)
- Multi-agent delegation issues (cycles, timeouts)

## Phase Roadmap

- ✅ **Phase 1**: Core agent loop enhancements (retry, caching, parallel execution, observability)
- ✅ **Phase 2**: Multi-agent system (specialized agents with delegation)
- ✅ **Phase 3**: Conversation persistence (save/load sessions, auto-save)
- 📝 **Phase 4**: Multi-provider support (OpenAI, Claude, DeepSeek)
- 🔮 **Phase 5**: Long-term memory (vector store for semantic search)

## Plan Mode

- Make the plan extremely concise. Sacrifice grammar for the sake of concision.
- At the end of each plan, give me a list of unresolved questions to answer, if any.
