# LinkedIn Tools Reference

Canonical contract for LinkedIn browser tools in `resume_agent/tools/linkedin_tools.py`.
Last updated: 2026-03-02.

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
| `include_jd` | boolean | No | `false` | Fetch per-job JD snippets in the same call. |
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

## Reliability (CDP Runtime)

Chrome lifecycle is handled inside Python CDP runtime (`resume_agent/tools/cdp_client.py`), which handles:

- **Chrome quit before sync**: On macOS/Linux, if Chrome is already running, runtime attempts to quit it first and waits briefly for profile lock release.
- **Profile sync**: Copies cookies and login data from the real Chrome installation so LinkedIn sees an authenticated session.
- **Anti-detection flags**: `--disable-blink-features=AutomationControlled`, `--no-first-run`, `--no-default-browser-check`.
- **Debug port polling**: Polls `/json/version` until ready (30s timeout).
- **Dynamic free port**: Picks a free port when auto-launching.

Port behavior:

- `cdp.port = 0` (default): auto-launch path picks a free debug port.
- `cdp.port > 0`: runtime first tries connecting to that fixed port.
- If fixed-port connect fails and `cdp.auto_launch=true`, runtime may relaunch Chrome on an available port.

## Validation and Error Semantics

Common validation rules:

- Missing required args are rejected before tool execution.
- `job_detail` rejects invalid/non-LinkedIn URLs with:
  - `Invalid job_url. Expected LinkedIn job URL like https://www.linkedin.com/jobs/view/<job_id>/`
- Both tools run a LinkedIn login preflight check and return login guidance when session is not authenticated.

## Configuration

LinkedIn tools read from the top-level `cdp` config:

```yaml
cdp:
  port: 0                # 0 = auto-detect free port; nonzero = fixed
  chrome_profile: "~/.resume-agent/chrome-profile"
  auto_launch: true
```

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `cdp.port` | integer | `0` | `0` = auto-detect free port. Nonzero = try fixed port first |
| `cdp.auto_launch` | boolean | `true` | Launch Chrome automatically if not running |

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
