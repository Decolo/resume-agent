# Architecture Overview

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
# Run tests (if pytest is installed)
pytest

# Run with async support
pytest -v
```

## Architecture

### Core Components

1. **LLM Client (`llm.py`)**:
   - Uses Google GenAI SDK (not OpenAI-compatible API)
   - Implements `GeminiAgent` class with native function calling
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

4. **Agent Loop (`agent.py`)**:
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
  - Config loaded from `config/config.yaml`
  - API key can be in config file or environment variable (`GEMINI_API_KEY`)
  - Supports `${ENV_VAR}` syntax in config for environment variable substitution

## Configuration

### API Setup

The agent uses Google Gemini by default. Edit `config/config.yaml`:

```yaml
api_key: "your-gemini-api-key"  # or ${GEMINI_API_KEY}
model: "gemini-2.5-flash"       # or gemini-2.0-flash, gemini-1.5-pro
max_tokens: 4096
temperature: 0.7
```

Environment variables:
- `GEMINI_API_KEY`: Gemini API key (primary)
- `OPENAI_API_KEY`: Fallback if Gemini not configured

### Important Notes

- **Not OpenAI-compatible**: Despite the README mentioning OpenAI support, the current implementation (`llm.py`) only supports Google GenAI SDK
- **Workspace Directory**: Agent operates within a workspace directory (default: current directory)
- **File Formats**: Resume parser supports PDF, DOCX, Markdown, TXT, JSON; writer supports MD, TXT, JSON, HTML

## File Structure

```
resume_agent/
├── agent.py              # ResumeAgent class, tool initialization
├── llm.py                # GeminiAgent with function calling, HistoryManager
├── cli.py                # Interactive CLI with Rich/prompt-toolkit
├── retry.py              # Retry logic with exponential backoff + jitter
├── observability.py      # Structured logging and metrics collection
├── cache.py              # Tool result caching with TTL
├── tools/
│   ├── base.py           # BaseTool abstract class, ToolResult (with metadata)
│   ├── file_tool.py      # File read/write/list tools (with size/binary checks)
│   ├── bash_tool.py      # Shell command execution (with enhanced security)
│   ├── resume_parser.py  # Multi-format resume parsing (with mtime caching)
│   └── resume_writer.py  # Multi-format resume generation
└── skills/
    └── resume_expert.py  # System prompt with resume expertise

tests/
└── test_phase1_improvements.py  # Comprehensive test suite (28 tests)
```

## CLI Commands

When running interactively:
- `/help` - Show help message
- `/reset` - Reset conversation history
- `/quit` or `/exit` - Exit the agent
- `/files` - List files in workspace
- `/config` - Show current configuration
