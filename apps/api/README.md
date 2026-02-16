# apps/api

Phase 3 (Slice D) scaffold for API app entrypoint ownership in the target monorepo layout.

Current compatibility policy:

1. FastAPI app source lives in `apps/api/resume_agent_api/app.py`.
2. `resume_agent/web/app.py` remains a compatibility shim forwarding to this module.
3. API routers/store still live under `resume_agent/web/*` until follow-up slices.
