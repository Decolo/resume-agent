# Resume Agent

An AI-powered resume modification agent built on open-source LLM agent technology. This project demonstrates how to build a practical agent with tools that connect LLMs to local filesystem operations.

## Features

- 📄 **Multi-format Support**: Parse and generate resumes in PDF, DOCX, Markdown, JSON, HTML
- 🔧 **Tool-based Architecture**: Modular tools for file operations, resume parsing, and generation
- 🤖 **Multiple LLM Backends**: Gemini by default, with an OpenAI-compatible client available
- 💬 **Interactive CLI**: Rich command-line interface with conversation history
- 📝 **Resume Expert Knowledge**: Built-in expertise for ATS optimization, action verbs, and best practices

## 📚 Documentation

Complete documentation is available in the `/docs` directory:

- **[Environment Setup](./docs/setup/environment-setup.md)** - API keys and local config
- **[Session Persistence](./docs/sessions/session-persistence.md)** - Save and restore sessions
- **[Export History](./docs/usage/export-history.md)** - Save or copy conversation history
- **[LinkedIn Tools Reference](./docs/api-reference/linkedin-tools.md)** - Contracts for `job_search` / `job_detail`
- **[Architecture Overview](./CLAUDE.md)** - System design and components (Claude Code instructions)
- **[Phase 1 Improvements (Archived)](./docs/archive/phase1-improvements.md)** - Historical technical improvements
- **[API Reference](./docs/api-reference/phase1-quick-reference.md)** - Code examples and API usage
- **Examples Folder** - Sample resumes and workspaces live in `./examples/`

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

Edit `config/config.local.yaml` (default) or set an environment variable:

```bash
export GEMINI_API_KEY="your-gemini-api-key"
```

### 3. Run the Agent

```bash
# Interactive mode (recommended)
uv run resume-agent --workspace ./examples/my_resume

# Or with Python
uv run python -m resume_agent.cli.app
```

For detailed instructions, see [Documentation Index](./docs/README.md).

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
│   ├── cli/           # CLI app entrypoint
│   ├── core/          # Agent runtime, LLM orchestration
│   ├── domain/        # Pure domain logic (resume parsing, ATS scoring, etc.)
│   ├── providers/     # LLM provider adapters
│   └── tools/         # Tool adapters (file I/O, bash, resume tools)
├── tests/
│   ├── architecture/  # Boundary & packaging guardrails
│   ├── cli/           # CLI tests
│   ├── core/          # Core runtime tests
│   ├── domain/        # Domain logic tests
│   └── tools/         # Tool adapter tests
├── config/
│   ├── config.local.yaml # Local config (default, keep secrets here)
│   └── config.yaml       # Optional shared defaults
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
| `job_search` | Search LinkedIn jobs by keywords/location (supports pagination and optional JD snippets) |
| `job_detail` | Fetch one LinkedIn job detail from explicit `job_url` |

## Architecture

This agent follows the standard **LLM Agent Loop**:

```
User Input → LLM (with tools) → Tool Calls → Tool Results → LLM → ... → Final Response
```

The key components are:

1. **CLI App** (`resume_agent/cli/`)
2. **Domain Logic** (`resume_agent/domain/`) - Pure functions for resume operations
3. **Core Runtime** (`resume_agent/core/`) - Agent orchestration and LLM integration
4. **Tools** (`resume_agent/tools/`) - Tool adapters for file I/O, bash, resume operations
5. **Provider Layer** (`resume_agent/providers/`)

## Supported LLM Providers

- **Google Gemini** is the default (via `resume_agent/providers/gemini.py`).
- **OpenAI-compatible endpoints** are provided by `resume_agent/providers/openai_compat.py`.

## Development

### Setup Development Environment

```bash
# Install with dev dependencies
uv sync

# Install pre-commit hooks (runs linting/formatting before commits)
uv run pre-commit install
```

### Code Quality Tools

```bash
# Run linter
uv run ruff check .

# Auto-fix linting issues
uv run ruff check --fix .

# Format code
uv run ruff format .

# Type checking
uv run mypy

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=resume_agent --cov-report=html
```

### Pre-commit Hooks

Pre-commit hooks automatically run before each commit to catch issues early:
- **ruff**: Linting and auto-fixes
- **ruff-format**: Code formatting
- **mypy**: Type checking (on configured files)
- **Standard checks**: Large files, merge conflicts, YAML syntax, trailing whitespace

To run manually on all files:
```bash
uv run pre-commit run --all-files
```

To bypass hooks (not recommended):
```bash
git commit --no-verify
```

## License

MIT License
