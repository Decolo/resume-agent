# LinkedIn Tools Reference

Canonical contract for LinkedIn browser tools in `resume_agent/tools/linkedin_tools.py`.
Last updated: 2026-03-01.

## Overview

This repo exposes two LinkedIn tools with intentionally separated responsibilities:

- `job_search`: discover jobs by keywords/location and return listing results.
- `job_detail`: fetch full detail for exactly one explicit LinkedIn job URL.

They are designed to avoid mixed intent in one tool call.

## Tool Contracts

### `job_search`

Use for broad discovery queries only, for example:

- "Front Engineer in China"
- "React Developer in Shanghai"

Parameters:

| Name | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `keywords` | string | Yes | N/A | Search keywords/title. |
| `location` | string | No | `""` | Optional location filter. |
| `limit` | integer | No | `25` | `1..100`. Tool auto-paginates when needed. |
| `include_jd` | boolean | No | driver-dependent | If omitted: enabled by default on Patchright driver, disabled on CDP driver. |
| `detail_workers` | integer | No | `2` | Positive integer. Used when fetching JD snippets (`include_jd=true`). |

Output behavior:

- Returns formatted text output and structured `data.jobs[]`.
- Each job item includes:
  - `title`, `company`, `location`
  - `job_id`, `url`, `posted_time`
  - `jd` (JD snippet if fetched)
- Dedupe key: `job_id`, then `url`, then `title|company|location`.

### `job_detail`

Use only when the input already contains one concrete LinkedIn job URL.

Parameters:

| Name | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `job_url` | string | Yes | N/A | Must match LinkedIn format: `https://www.linkedin.com/jobs/view/<id>/...` |

Output behavior:

- Returns formatted full detail text and structured fields in `data`, including:
  - `title`, `company`, `location`
  - `description`
  - `url`, `posted_time`
  - `seniority_level`, `employment_type`

## Runtime Policy (Important)

`LLMAgent` enforces a hard policy:

- If `job_search` and `job_detail` are requested in the same step, `job_detail` is rejected for that step.
- Rejection reason is added as a tool response:
  - `Rejected by policy: job_detail cannot run in the same step as job_search...`

Recommended flow:

1. Run `job_search` first (optionally with `include_jd=true`).
2. Select a specific job URL from search results.
3. Run `job_detail` in a later step with `job_url`.

## Pagination and Anti-Bot Behavior

`job_search` includes human-like pacing:

- Random delay between pagination actions: `0.6s ~ 1.8s`.
- If click-based pagination fails, tool falls back to URL-offset pagination.
- When JD snippets are fetched, each detail request adds small jitter (`0.15s ~ 0.45s`).

These delays are intentional to reduce robotic access patterns.

## Validation and Error Semantics

Common validation rules:

- Missing required args are rejected before tool execution.
- `job_detail` rejects invalid/non-LinkedIn URLs with:
  - `Invalid job_url. Expected LinkedIn job URL like https://www.linkedin.com/jobs/view/<job_id>/`
- Both tools run a LinkedIn login preflight check and return login guidance when session is not authenticated.

## Driver Configuration

LinkedIn tools support:

- `cdp` (default)
- `patchright` (or `playwright` alias in code path)

Example config:

```yaml
linkedin:
  driver: "cdp" # cdp | patchright
  patchright:
    headless: false
    channel: "chrome"
    auto_launch: true
```

CDP defaults are inherited from top-level `cdp.*` unless overridden in `linkedin.cdp.*`.

## Examples

Search:

```json
{
  "name": "job_search",
  "arguments": {
    "keywords": "Front Engineer",
    "location": "China",
    "limit": 40,
    "include_jd": true
  }
}
```

Detail:

```json
{
  "name": "job_detail",
  "arguments": {
    "job_url": "https://www.linkedin.com/jobs/view/4353119521/"
  }
}
```
