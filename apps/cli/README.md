# apps/cli

Phase 3 (Slice E) scaffold for CLI app entrypoint ownership in the target monorepo layout.

Current compatibility policy:

1. CLI app source lives in `apps/cli/resume_agent_cli/app.py`.
2. `resume_agent/cli.py` remains a compatibility shim forwarding to this module.
3. `uv run resume-agent` keeps using `resume_agent.cli:main` during migration.
