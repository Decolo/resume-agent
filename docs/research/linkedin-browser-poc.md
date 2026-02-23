# LinkedIn Browser PoC (Standalone)

This PoC is intentionally standalone and **not integrated** into `resume-agent` CLI.

Script: `scripts/linkedin_jobs_poc.py`

## What It Does

- Persisted login session (manual login once)
- Collect job cards from LinkedIn jobs search pages
- Optionally open each job URL and extract detail fields
- Export JSONL for later matching pipeline

## Prerequisites

1. Install Playwright:

```bash
uv pip install playwright
uv run playwright install chromium
```

2. Make sure your local network can access `linkedin.com`.

## Commands

### 1) Login once (session bootstrap)

```bash
uv run python scripts/linkedin_jobs_poc.py login
```

- Browser window opens.
- Log in manually.
- Return to terminal and press `Enter`.
- Session is persisted in `workspace/linkedin_poc/profile/`.

### 2) Collect job summaries

```bash
uv run python scripts/linkedin_jobs_poc.py collect \
  --keywords "software engineer" \
  --location "San Francisco Bay Area" \
  --pages 2
```

Output (example):
- `workspace/linkedin_poc/outputs/linkedin_jobs_YYYYMMDD_HHMMSS.jsonl`

### 3) Collect details from collected summaries

```bash
uv run python scripts/linkedin_jobs_poc.py details \
  --input workspace/linkedin_poc/outputs/linkedin_jobs_YYYYMMDD_HHMMSS.jsonl
```

### 4) One-shot collect + details

```bash
uv run python scripts/linkedin_jobs_poc.py collect \
  --keywords "data scientist" \
  --location "New York" \
  --pages 1 \
  --with-details \
  --max-details 20
```

## Output Fields

Summary JSONL fields:
- `source`
- `collected_at`
- `job_id`
- `job_url`
- `title`
- `company`
- `location`
- `posted_text`

Detail JSONL fields include summary fields plus:
- `employment_type`
- `seniority`
- `description_text`
- `apply_url`

## Notes / Constraints

- This is a PoC parser and LinkedIn DOM can change.
- Keep runs low-frequency and user-triggered.
- If login wall/captcha appears, stop and re-run `login`.
- Do not treat this as production-grade crawling yet.
