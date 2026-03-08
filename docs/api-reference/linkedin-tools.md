# LinkedIn Tools Reference

Canonical contract for LinkedIn browser tools in `resume_agent/tools/linkedin_tools.py`.
Last updated: 2026-03-07.

## Overview

This repo currently exposes one LinkedIn tool:

- `job_search`: discover jobs by keywords/location and return listing results.

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
| `include_jd` | boolean | No | `false` | Click each card and extract JD from the right pane. |

Output behavior:

- Two modes based on `include_jd`:
  - `include_jd=false` (fast path): Scrolls the left column to load all cards, collects metadata (title, company, location, posted_time, URL) from card DOM elements, then clicks "Next" to paginate.
  - `include_jd=true` (detail path): Scrolls the left column, then clicks each card and waits for the right pane to load. Extracts title, company, location, posted_time, URL, and JD snippet from the right pane.
- Returns formatted text output and structured `data.jobs[]`.
- Each job item includes:
  - `title`, `company`, `location`
  - `job_id`, `url`, `posted_time`
  - `jd` (JD snippet if fetched)
- Dedupe key: `job_id`, then `url`, then `title|company|location`.

## Pagination and Anti-Bot Behavior

`job_search` uses a scroll-then-paginate approach:

- Scrolls the left-column container (not `window`) by 400px increments with 0.5–1.0s jitter to trigger lazy loading.
- Detects scroll stall (scrollHeight unchanged after 2 iterations) and scroll bottom to stop.
- After collecting all cards on a page, clicks "Next" using a two-tier strategy:
  - **Tier 1 — Accessibility Tree (fast, no LLM cost):** Uses CDP `Accessibility.getFullAXTree` to find a `role=button/link` node whose `name` matches pagination keywords ("next", "next page", "下一页", etc.) and is not disabled. Clicks via `backendDOMNodeId`. This is independent of CSS class names.
  - **Tier 2 — LLM fallback (when AX tree has no match):** Collects all interactive elements (buttons + links with text/aria-labels) via JS, sends them to `gemini-2.5-flash` asking which is the pagination Next button. Only triggered when Tier 1 misses. Requires `api_key` in config.
- Polls for page change by comparing card URLs after clicking Next.
- Random delay between pagination actions: `0.6s ~ 1.8s`.
- When `include_jd=true`, each card click adds small jitter (`0.3s ~ 0.8s`).

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
- `job_search` rejects missing/invalid `keywords` and out-of-range `limit`.
- `job_search` runs a LinkedIn login preflight check and returns login guidance when session is not authenticated.

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
| `api_key` | string | `""` | Gemini API key. Enables LLM pagination fallback (Tier 2) when set |

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
