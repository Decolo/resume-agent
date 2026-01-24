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
resume-agent

# Or with Python module
python -m resume_agent.cli

# Single prompt mode (non-interactive)
resume-agent --prompt "Analyze the resume in examples/sample_resumes/sample_resume.md"

# Specify workspace directory
resume-agent --workspace /path/to/resumes

# Quiet mode (minimal output)
resume-agent --quiet
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
   - Manages conversation history as `types.Content` objects
   - Automatically executes tool calls in a loop until completion

2. **Agent Loop (`agent.py`)**:
   - `ResumeAgent` orchestrates the conversation
   - Initializes and registers all tools with the Gemini agent
   - Tools are registered with their schemas and execution functions
   - Max steps default: 50 iterations

3. **Tools System (`tools/`)**:
   - All tools inherit from `BaseTool` abstract class
   - Tools return `ToolResult` objects with success/error status
   - Tool execution can be sync or async (agent handles both)
   - Available tools:
     - `file_read`, `file_write`, `file_list`: Basic file operations
     - `bash`: Shell command execution
     - `resume_parse`: Parse PDF/DOCX/MD/JSON resumes (uses PyMuPDF, python-docx)
     - `resume_write`: Generate MD/TXT/JSON/HTML output

4. **System Prompt (`skills/resume_expert.py`)**:
   - Contains `RESUME_EXPERT_PROMPT` with resume writing expertise
   - Includes ATS optimization guidelines, action verbs, STAR method
   - Defines the agent's workflow and writing guidelines

### Key Architectural Details

- **Function Calling**: Uses Google GenAI SDK's native function calling (not OpenAI format)
  - Parameters are converted from OpenAI-style to Gemini `types.Schema` format
  - Function responses are wrapped in `types.Part.from_function_response()`
  - History is maintained as list of `types.Content` objects

- **Tool Registration**: Tools define parameters in OpenAI format, but `agent.py` converts them to Gemini format when registering with `GeminiAgent.register_tool()`

- **Async Execution**: The agent loop is fully async, and tools can be either sync or async (detected with `asyncio.iscoroutinefunction()`)

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
├── llm.py                # GeminiAgent with function calling
├── cli.py                # Interactive CLI with Rich/prompt-toolkit
├── tools/
│   ├── base.py           # BaseTool abstract class, ToolResult
│   ├── file_tool.py      # File read/write/list tools
│   ├── bash_tool.py      # Shell command execution
│   ├── resume_parser.py  # Multi-format resume parsing
│   └── resume_writer.py  # Multi-format resume generation
└── skills/
    └── resume_expert.py  # System prompt with resume expertise
```

## CLI Commands

When running interactively:
- `/help` - Show help message
- `/reset` - Reset conversation history
- `/quit` or `/exit` - Exit the agent
- `/files` - List files in workspace
- `/config` - Show current configuration


## Plan Mode

- Make the plan extremely concise. Sacrifice grammar for the sake of concision.
- At the end of each plan, give me a list of unresolved questions to answer, if any.