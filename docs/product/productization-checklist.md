# Productization Checklist

## Reliability & Trust
- Add an output verification step: check file existence and sizes, then report paths.
- Retry on empty LLM responses and tool-call loops; fall back to the last tool result when needed.
- Provide clear error messages: what failed, where, and actionable next steps.

## Determinism & UX
- Offer a dry-run/preview mode before writing files.
- Record inputs + outputs to allow reproducible runs.
- Keep Markdown/HTML/JSON output schemas stable across versions.

## User Journey
- One-click flow: import → improve → export with sensible defaults.
- Include sample resumes and templates for fast onboarding.
- Provide a “what changed” summary or diff after modifications.

## Observability
- Show a user-facing summary: files created, locations, elapsed time.
- Keep logs quiet by default, with a verbose toggle for debugging.

## Privacy & Safety
- Clearly document PII handling (local processing vs API calls).
- Add a config flag for local-only processing or explicit upload consent.

## Performance
- Default to single-agent; use multi-agent only for multi-format or batch jobs.
- Cap token usage and history length to reduce latency.

## Packaging
- Maintain a stable CLI interface and versioned config.
- Keep a non-engineer quickstart in README.
