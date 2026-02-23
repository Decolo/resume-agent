# Repository Guidelines

## Project Structure & Module Organization

### Apps (Entry Points)
- `apps/cli/resume_agent_cli/` - Interactive CLI with rich terminal UI
- `apps/web-next/` - Next.js 16 web application
  - Frontend: React with Vercel AI SDK for streaming chat
  - Backend: API routes with Cloudflare D1 (SQLite) + R2 (object storage)
  - Deployment: Cloudflare Pages

### Packages (Core Logic)
- `packages/domain/resume_agent_domain/` - Pure domain logic
  - `resume_parser.py`, `resume_writer.py`, `ats_scorer.py`, `job_matcher.py`, `resume_validator.py`
  - Pure functions with no external dependencies
  - All prompts in `prompts/` subdirectory
- `packages/core/resume_agent_core/` - Agent runtime
  - LLM orchestration, multi-agent system, session management
  - Caching, retry logic, observability
- `packages/tools/` - Environment-specific tool adapters
  - `cli/resume_agent_tools_cli/` - File I/O, bash execution, resume tools for CLI
  - `web/resume_agent_tools_web/` - JSON updates, export, analysis tools for web
- `packages/providers/resume_agent_providers/` - LLM provider adapters
- `packages/contracts/resume_agent_contracts/` - Shared types and contracts

### Configuration & Data
- `config/` - Runtime configuration (`config.local.yaml` is default, `config.yaml` is fallback)
- `tests/` - pytest test suites
- `docs/` - Documentation
- `examples/` - Sample resumes
- `workspace/sessions/` - Runtime session data (gitignored)

## Build, Test, and Development Commands

### Python (CLI)
```bash
# Install dependencies (recommended)
uv sync

# Alternative editable install
pip install -e .

# Run the CLI
uv run resume-agent --workspace ./examples/my_resume

# Run via module
uv run python -m apps.cli.resume_agent_cli.app

# Run tests
uv run pytest
```

### TypeScript (Web)
```bash
cd apps/web-next

# Install dependencies
pnpm install

# Run dev server
pnpm dev

# Build for production
pnpm build

# Type check
pnpm tsc --noEmit
```

## Architecture Principles

### Dependency Direction
1. `apps/*` → `packages/core` + `packages/tools/*`
2. `packages/tools/*` → `packages/domain` + `packages/core`
3. `packages/core` → `packages/providers`
4. `packages/domain` → **no dependencies** (pure functions)
5. `packages/*` must not depend on `apps/*`

### Tool Design Philosophy
- **CLI tools**: File-based operations (read/write entire files, bash execution)
- **Web tools**: API-based operations (JSON path updates, structured responses)
- Both call the same domain functions but with different I/O semantics

### Domain Layer Rules
- All domain functions must be pure (no side effects, no external dependencies)
- Return structured dataclasses, not strings
- Testable without LLM or file system

## Coding Style & Naming Conventions

### Python
- 4-space indentation
- `snake_case` for functions/variables/modules
- `PascalCase` for classes
- Type hints for public APIs
- Docstrings for public functions

### TypeScript
- 2-space indentation
- `camelCase` for functions/variables
- `PascalCase` for components/classes/types
- Explicit return types for exported functions

## Testing Guidelines

### Python Tests
- Tests live in `tests/` and use `pytest` with `pytest-asyncio`
- Name tests `test_*.py` with functions `test_*`
- Run: `uv run pytest`

### TypeScript Tests
- Component tests with React Testing Library
- API route tests with MSW (Mock Service Worker)
- Run: `pnpm test` (when configured)

## Commit & Pull Request Guidelines

- Commit messages follow Conventional Commits:
  - `feat:` - New features
  - `fix:` - Bug fixes
  - `refactor:` - Code restructuring
  - `chore:` - Maintenance tasks
  - `docs:` - Documentation updates
- PRs should include:
  - Clear summary of changes
  - Test results
  - Sample outputs for resume formatting changes

## Security & Configuration Notes

- Store API keys in `config/config.local.yaml` or environment variables
- **Never commit secrets**
- Resume files contain PII—avoid committing real resumes
- Session files contain full conversations—do not commit `workspace/sessions/`
- Web app stores API keys in browser localStorage (client-side only)

## Session Persistence

### CLI Sessions
- Saved as JSON under `workspace/sessions/` with `.index.json`
- Commands: `/save [name]`, `/load <id>`, `/sessions`, `/delete-session <id>`
- Auto-save enabled by default

### Web Sessions
- Stored in Cloudflare D1 (SQLite database)
- Includes `resumeJson`, `workflowState`, `provider` settings
- Persisted automatically on every change

## Web App Architecture

### Frontend
- Next.js 16 App Router
- Vercel AI SDK v6 for streaming chat
- shadcn/ui components with Tailwind CSS
- Zustand for resume state management
- React Query for server state

### Backend
- API routes in `src/app/api/`
- Cloudflare D1 for session/message storage
- Cloudflare R2 for file uploads
- Drizzle ORM for type-safe queries

### Multi-Provider LLM Support
- Gemini (native Google AI)
- OpenAI (including compatible providers: Kimi/Moonshot, DeepSeek, etc.)
- Custom base URL and model ID support
- **Important**: Use `.chat()` method for OpenAI-compatible providers (not default `()` which uses Responses API)

## Plan Mode

- Make the plan extremely concise. Sacrifice grammar for the sake of concision.
- At the end of each plan, give me a list of unresolved questions to answer, if any.
