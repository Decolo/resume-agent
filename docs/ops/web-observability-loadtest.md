# Web Observability and Load Test

This guide covers runtime metrics/alerts and local load testing for Web API v1.

## Runtime Metrics Endpoint

Use:

```bash
curl -s http://127.0.0.1:8000/api/v1/settings/metrics | jq
```

Response includes:

- queue depth (`queue_depth`)
- pending approvals (`pending_approvals`)
- run counters (`runs_total`, `runs_active`, `runs_completed`, `runs_failed`, `runs_interrupted`)
- latency (`avg_latency_ms`, `p95_latency_ms`)
- cost telemetry (`total_tokens`, `total_estimated_cost_usd`)

## Runtime Alerts Endpoint

Use:

```bash
curl -s http://127.0.0.1:8000/api/v1/settings/alerts | jq
```

Each alert item has:

- `name` metric key
- `status` (`ok` or `alert`)
- `value` current measured value
- `threshold` configured threshold
- `message` human-readable reason

### Alert Threshold Env Vars

- `RESUME_AGENT_WEB_ALERT_MAX_ERROR_RATE` (default `0.2`)
- `RESUME_AGENT_WEB_ALERT_MAX_P95_LATENCY_MS` (default `15000`)
- `RESUME_AGENT_WEB_ALERT_MAX_TOTAL_COST_USD` (default `10`)
- `RESUME_AGENT_WEB_ALERT_MAX_QUEUE_DEPTH` (default `50`)

## Local Load Test Script

Run API first:

```bash
uv run python -m apps.api.resume_agent_api.app
```

Then run load test:

```bash
uv run python scripts/loadtest_web_api.py --base-url http://127.0.0.1:8000 --concurrency 10 --runs 50
```

Optional:

- `--tenant-id tenant-a` for tenant-scoped load
- `--message "Update resume.md"` for write-heavy runs

Output example:

```text
{'runs': 50, 'success': 50, 'failures': 0, 'avg_ms': 142.6, 'p95_ms': 196.1, 'max_ms': 221.3}
```
