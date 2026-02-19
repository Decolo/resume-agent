# apps/cli

CLI application entrypoint package.

Ownership:

1. CLI runtime lives in `apps/cli/resume_agent_cli/app.py`.
2. Project script `resume-agent` points directly to `apps.cli.resume_agent_cli.app:main`.
3. Legacy `resume_agent/cli.py` shim has been retired.
