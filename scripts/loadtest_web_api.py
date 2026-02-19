#!/usr/bin/env python3
"""Basic local load-test runner for Resume Agent Web API."""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from typing import Any

import httpx


async def _run_once(client: httpx.AsyncClient, base_url: str, message: str) -> float:
    start = time.perf_counter()
    session_resp = await client.post(f"{base_url}/api/v1/sessions", json={"auto_approve": True})
    session_resp.raise_for_status()
    session_id = session_resp.json()["session_id"]

    run_resp = await client.post(
        f"{base_url}/api/v1/sessions/{session_id}/messages",
        json={"message": message},
    )
    run_resp.raise_for_status()
    run_id = run_resp.json()["run_id"]

    stream_resp = await client.get(
        f"{base_url}/api/v1/sessions/{session_id}/runs/{run_id}/stream",
        headers={"Accept": "text/event-stream"},
        timeout=60.0,
    )
    stream_resp.raise_for_status()
    _ = stream_resp.text
    return (time.perf_counter() - start) * 1000.0


async def run_load_test(
    base_url: str,
    concurrency: int,
    runs: int,
    message: str,
    tenant_id: str | None,
) -> dict[str, Any]:
    sem = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    failures = 0

    headers = {"X-Tenant-ID": tenant_id} if tenant_id else {}
    async with httpx.AsyncClient(headers=headers) as client:

        async def one_job() -> None:
            nonlocal failures
            async with sem:
                try:
                    latency = await _run_once(client, base_url, message)
                    latencies.append(latency)
                except Exception:
                    failures += 1

        await asyncio.gather(*[one_job() for _ in range(runs)])

    latencies.sort()
    if not latencies:
        return {
            "runs": runs,
            "success": 0,
            "failures": failures,
            "avg_ms": 0.0,
            "p95_ms": 0.0,
            "max_ms": 0.0,
        }
    p95_idx = max(0, int((len(latencies) - 1) * 0.95))
    return {
        "runs": runs,
        "success": len(latencies),
        "failures": failures,
        "avg_ms": round(statistics.mean(latencies), 2),
        "p95_ms": round(latencies[p95_idx], 2),
        "max_ms": round(latencies[-1], 2),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run lightweight load test against local Web API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--runs", type=int, default=50)
    parser.add_argument("--message", default="Summarize resume content")
    parser.add_argument("--tenant-id", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = asyncio.run(
        run_load_test(
            base_url=args.base_url.rstrip("/"),
            concurrency=max(args.concurrency, 1),
            runs=max(args.runs, 1),
            message=args.message,
            tenant_id=args.tenant_id.strip() or None,
        )
    )
    print(result)


if __name__ == "__main__":
    main()
