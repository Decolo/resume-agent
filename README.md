# Resume Agent

An AI-powered resume modification agent built on open-source LLM agent technology. This project demonstrates how to build a practical agent with tools that connect LLMs to local filesystem operations.

## Features

- 📄 **Multi-format Support**: Parse and generate resumes in PDF, DOCX, Markdown, JSON, HTML
- 🔧 **Tool-based Architecture**: Modular tools for file operations, resume parsing, and generation
- 🤖 **Multiple LLM Backends**: Works with Google Gemini, OpenAI, Anthropic, or any OpenAI-compatible API
- 💬 **Interactive CLI**: Rich command-line interface with conversation history
- 📝 **Resume Expert Knowledge**: Built-in expertise for ATS optimization, action verbs, and best practices

## 📚 Documentation

Complete documentation is available in the `/docs` directory:

- **[Quick Start](./docs/quick-start.md)** - Get running in 3 steps
- **[Getting Started Guide](./docs/getting-started.md)** - Comprehensive setup and configuration
- **[How to Run](./docs/how-to-run.md)** - Multiple ways to launch the agent
- **[Architecture Overview](./.claude/CLAUDE.md)** - System design and components (Claude Code instructions)
- **[Phase 1 Improvements](./docs/architecture/phase1-improvements.md)** - Technical improvements
- **[API Reference](./docs/api-reference/phase1-quick-reference.md)** - Code examples and API usage
- **[Workspace Guide](./docs/workspace/my-resume-guide.md)** - Using the example workspace

## Quick Start

### 1. Install Dependencies

```bash
cd resume-agent

# Using uv (recommended)
uv sync

# Or using pip
pip install -e .
```

### 2. Configure API Key

Edit `config/config.yaml` or set environment variable:

```bash
export GEMINI_API_KEY="your-gemini-api-key"
```

### 3. Run the Agent

```bash
# Interactive mode (recommended)
uv run resume-agent --workspace ./examples/my_resume

# Or with Python
uv run python -m resume_agent.cli

# Single prompt mode
uv run resume-agent --prompt "Parse my resume and analyze it"
```

For detailed instructions, see [Quick Start Guide](./docs/quick-start.md).

## Usage Examples

### Analyze a Resume
```
📝 You: Parse my resume from examples/sample_resumes/sample_resume.md and give me feedback
```

### Improve Work Experience
```
📝 You: Improve the bullet points in my experience section with stronger action verbs and quantifiable metrics
```

### Tailor for a Job
```
📝 You: Tailor my resume for a Senior Backend Engineer position at Google, focusing on distributed systems experience
```

### Convert Format
```
📝 You: Convert my resume to a modern HTML format and save it as output/resume.html
```

## Project Structure

```
resume-agent/
├── resume_agent/
│   ├── __init__.py
│   ├── agent.py          # Core agent loop
│   ├── llm.py            # LLM client (OpenAI-compatible)
│   ├── cli.py            # Command-line interface
│   ├── tools/
│   │   ├── base.py           # Base tool class
│   │   ├── file_tool.py      # File read/write/list
│   │   ├── bash_tool.py      # Shell command execution
│   │   ├── resume_parser.py  # PDF/DOCX/MD parsing
│   │   └── resume_writer.py  # Multi-format output
│   └── skills/
│       └── resume_expert.py  # System prompt
├── config/
│   └── config.yaml       # Configuration
├── examples/
│   └── sample_resumes/   # Example resumes
├── pyproject.toml
└── README.md
```

## Tools

| Tool | Description |
|------|-------------|
| `file_read` | Read text file contents |
| `file_write` | Write content to files |
| `file_list` | List directory contents |
| `bash` | Execute shell commands |
| `resume_parse` | Parse PDF/DOCX/MD/JSON resumes |
| `resume_write` | Generate MD/TXT/JSON/HTML output |

## Architecture

This agent follows the standard **LLM Agent Loop**:

```
User Input → LLM (with tools) → Tool Calls → Tool Results → LLM → ... → Final Response
```

The key components are:

1. **LLM Client** (`llm.py`): Handles communication with OpenAI-compatible APIs
2. **Tools** (`tools/`): Connect the LLM to local system capabilities
3. **Agent Loop** (`agent.py`): Orchestrates the conversation and tool execution
4. **System Prompt** (`skills/`): Provides domain expertise

## Supported LLM Providers

| Provider | API Base | Models |
|----------|----------|--------|
| **Google Gemini** | `generativelanguage.googleapis.com/v1beta` | gemini-2.0-flash, gemini-1.5-pro |
| **OpenAI** | `api.openai.com/v1` | gpt-4o, gpt-4-turbo |
| **Anthropic** | `api.anthropic.com` | claude-sonnet-4, claude-opus-4 |
| **MiniMax** | `api.minimax.io` | MiniMax-M2.1 |

## License

MIT License
