# LinkedIn Browser PoC (CDP)

This PoC is intentionally standalone and not integrated into the main
`resume-agent` CLI flow.

Implementation lives in:

- `poc/start-chrome.sh`
- `poc/cdp_client.js`
- `poc/linkedin_jobs.js`

## What It Does

- Reuses a persistent Chrome profile (manual LinkedIn login once)
- Connects via CDP (Chrome DevTools Protocol)
- Supports keyword-based job search page extraction
- Supports single job-detail page extraction by job id

## Prerequisites

1. Install JS dependencies:

```bash
cd poc
npm install
```

2. Launch Chrome with remote debugging and persistent profile:

```bash
./poc/start-chrome.sh
```

## Commands

### 1) Search jobs

```bash
node poc/linkedin_jobs.js search "Senior Frontend Engineer" --location "San Francisco"
```

### 2) Search (dry run)

```bash
node poc/linkedin_jobs.js search "React Developer" --dry-run
```

### 3) Job detail by id

```bash
node poc/linkedin_jobs.js detail 1234567890
```

### 4) Custom CDP port

```bash
node poc/linkedin_jobs.js search "Engineer" --port 9222
```

## Notes and Constraints

- LinkedIn page structure changes frequently; extraction quality may drift.
- Run at low frequency and user-triggered only.
- CDP grants full browser control; never expose debug port publicly.
- Profile data in `poc/.chrome-profile/` is sensitive and should stay local.
