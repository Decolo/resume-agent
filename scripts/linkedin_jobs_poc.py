#!/usr/bin/env python3
"""Standalone LinkedIn browser collector PoC (not integrated into resume-agent CLI).

This script uses a persisted browser profile so the user can log in once manually,
then reuse session cookies for low-frequency, user-triggered job collection.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote_plus

DEFAULT_ROOT = Path("workspace/linkedin_poc")
DEFAULT_PROFILE_DIR = DEFAULT_ROOT / "profile"
DEFAULT_OUTPUT_DIR = DEFAULT_ROOT / "outputs"

JOB_ID_RE = re.compile(r"/jobs/view/(\d+)")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_job_url(url: str) -> str:
    trimmed = (url or "").strip()
    if not trimmed:
        return ""
    trimmed = trimmed.split("?", 1)[0].split("#", 1)[0]
    return trimmed.rstrip("/") + "/"


def extract_job_id(url: str) -> str | None:
    match = JOB_ID_RE.search(url or "")
    return match.group(1) if match else None


def build_search_url(keywords: str, location: str, start: int = 0) -> str:
    base = "https://www.linkedin.com/jobs/search/"
    parts = [f"keywords={quote_plus(keywords.strip())}"]
    if location.strip():
        parts.append(f"location={quote_plus(location.strip())}")
    if start > 0:
        parts.append(f"start={start}")
    return f"{base}?{'&'.join(parts)}"


def dedupe_jobs(jobs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for job in jobs:
        url = canonical_job_url(str(job.get("job_url", "")))
        job_id = str(job.get("job_id") or "")
        key = job_id or url
        if not key or key in seen:
            continue
        seen.add(key)
        normalized = dict(job)
        normalized["job_url"] = url
        if not normalized.get("job_id"):
            normalized["job_id"] = extract_job_id(url)
        result.append(normalized)
    return result


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


@dataclass
class JobSummary:
    source: str
    collected_at: str
    job_id: str | None
    job_url: str
    title: str
    company: str
    location: str
    posted_text: str


@dataclass
class JobDetail:
    source: str
    collected_at: str
    job_id: str | None
    job_url: str
    title: str
    company: str
    location: str
    posted_text: str
    employment_type: str
    seniority: str
    description_text: str
    apply_url: str


async def sleep_with_jitter(min_delay: float, max_delay: float) -> None:
    if max_delay < min_delay:
        min_delay, max_delay = max_delay, min_delay
    await asyncio.sleep(random.uniform(min_delay, max_delay))


def _import_playwright():
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Install with: uv pip install playwright && uv run playwright install chromium"
        ) from exc
    return async_playwright


async def launch_context(profile_dir: Path, headless: bool):
    async_playwright = _import_playwright()
    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=headless,
        viewport={"width": 1440, "height": 1024},
    )
    return pw, context


async def ensure_page(context):
    if context.pages:
        return context.pages[0]
    return await context.new_page()


async def is_login_required(page) -> bool:
    url = page.url.lower()
    if "/login" in url or "authwall" in url:
        return True
    text = (await page.content()).lower()
    markers = ["join linkedin", "sign in", "new to linkedin"]
    return any(marker in text for marker in markers)


async def login_flow(profile_dir: Path, headless: bool) -> int:
    ensure_dir(profile_dir)
    pw, context = await launch_context(profile_dir, headless=headless)
    try:
        page = await ensure_page(context)
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

        if not await is_login_required(page):
            print("[ok] Existing LinkedIn login session detected.")
            return 0

        print("[action] Browser opened. Please log in to LinkedIn manually in that window.")
        print("[action] After login is complete and feed/jobs page is visible, press ENTER here.")
        await asyncio.to_thread(input)

        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        if await is_login_required(page):
            print("[error] Login still appears required. Please retry login command.")
            return 1

        print("[ok] Login session saved to profile directory.")
        return 0
    finally:
        await context.close()
        await pw.stop()


async def extract_search_cards(page) -> list[dict[str, Any]]:
    js = """
() => {
  const nodes = Array.from(document.querySelectorAll('a[href*="/jobs/view/"]'));
  const rows = [];
  for (const a of nodes) {
    const href = a.href || '';
    if (!href.includes('/jobs/view/')) continue;
    const card = a.closest('li') || a.closest('[data-occludable-job-id]') || a.closest('div');
    const title = (a.textContent || '').trim();
    let company = '';
    let location = '';
    let posted = '';
    if (card) {
      const meta = Array.from(card.querySelectorAll('span, div')).map(x => (x.textContent || '').trim()).filter(Boolean);
      if (meta.length > 0) company = meta[0] || '';
      if (meta.length > 1) location = meta[1] || '';
      posted = meta.find(x => /hour|day|week|month|just now|ago/i.test(x)) || '';
    }
    rows.push({ job_url: href, title, company, location, posted_text: posted });
  }
  return rows;
}
"""
    raw_rows = await page.evaluate(js)
    jobs: list[dict[str, Any]] = []
    for row in raw_rows:
        job_url = canonical_job_url(str(row.get("job_url", "")))
        job_id = extract_job_id(job_url)
        if not job_url or not job_id:
            continue
        jobs.append(
            asdict(
                JobSummary(
                    source="linkedin",
                    collected_at=utc_now_iso(),
                    job_id=job_id,
                    job_url=job_url,
                    title=str(row.get("title", "")).strip(),
                    company=str(row.get("company", "")).strip(),
                    location=str(row.get("location", "")).strip(),
                    posted_text=str(row.get("posted_text", "")).strip(),
                )
            )
        )
    return dedupe_jobs(jobs)


async def fetch_job_detail(page, job: dict[str, Any]) -> dict[str, Any]:
    url = canonical_job_url(str(job.get("job_url", "")))
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_timeout(1800)

    js = """
() => {
  const text = (sel) => {
    const el = document.querySelector(sel);
    return el ? (el.textContent || '').trim() : '';
  };

  const descriptionEl =
    document.querySelector('.show-more-less-html__markup') ||
    document.querySelector('[class*="jobs-description"]') ||
    document.querySelector('[id*="job-details"]');

  const applyLink = document.querySelector('a[href*="offsite-apply"], a[data-tracking-control-name*="public_jobs_apply-link"]');

  // Job criteria rows often appear as key/value in list items.
  let employmentType = '';
  let seniority = '';
  const criteriaRows = Array.from(document.querySelectorAll('li')).map(li => (li.textContent || '').trim());
  for (const row of criteriaRows) {
    const lower = row.toLowerCase();
    if (!employmentType && lower.includes('employment type')) employmentType = row;
    if (!seniority && lower.includes('seniority level')) seniority = row;
  }

  return {
    title: text('h1'),
    company: text('a[href*="/company/"], .topcard__org-name-link, [data-tracking-control-name*="public_jobs_topcard-org-name"]'),
    location: text('.topcard__flavor--bullet, .job-details-jobs-unified-top-card__bullet, [data-test-job-location]'),
    description_text: descriptionEl ? (descriptionEl.textContent || '').trim() : '',
    apply_url: applyLink ? (applyLink.href || '') : '',
    employment_type: employmentType,
    seniority: seniority,
  };
}
"""

    extracted = await page.evaluate(js)
    merged = dict(job)
    merged["source"] = "linkedin"
    merged["collected_at"] = utc_now_iso()
    merged["job_url"] = url
    merged["job_id"] = merged.get("job_id") or extract_job_id(url)
    merged["title"] = str(extracted.get("title") or merged.get("title") or "").strip()
    merged["company"] = str(extracted.get("company") or merged.get("company") or "").strip()
    merged["location"] = str(extracted.get("location") or merged.get("location") or "").strip()
    merged["posted_text"] = str(merged.get("posted_text") or "").strip()
    merged["employment_type"] = str(extracted.get("employment_type") or "").strip()
    merged["seniority"] = str(extracted.get("seniority") or "").strip()
    merged["description_text"] = str(extracted.get("description_text") or "").strip()
    merged["apply_url"] = canonical_job_url(str(extracted.get("apply_url") or ""))
    return asdict(
        JobDetail(
            source=merged["source"],
            collected_at=merged["collected_at"],
            job_id=merged.get("job_id"),
            job_url=merged.get("job_url", ""),
            title=merged.get("title", ""),
            company=merged.get("company", ""),
            location=merged.get("location", ""),
            posted_text=merged.get("posted_text", ""),
            employment_type=merged.get("employment_type", ""),
            seniority=merged.get("seniority", ""),
            description_text=merged.get("description_text", ""),
            apply_url=merged.get("apply_url", ""),
        )
    )


async def collect_jobs(
    profile_dir: Path,
    keywords: str,
    location: str,
    pages: int,
    headless: bool,
    min_delay: float,
    max_delay: float,
) -> list[dict[str, Any]]:
    ensure_dir(profile_dir)
    pw, context = await launch_context(profile_dir, headless=headless)
    try:
        page = await ensure_page(context)
        jobs: list[dict[str, Any]] = []

        for index in range(pages):
            start = index * 25
            search_url = build_search_url(keywords, location, start=start)
            print(f"[collect] page={index + 1}/{pages} start={start} url={search_url}")
            await page.goto(search_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)

            if await is_login_required(page):
                raise RuntimeError("LinkedIn login is required. Run `login` command first.")

            page_jobs = await extract_search_cards(page)
            print(f"[collect] extracted {len(page_jobs)} job links")
            jobs.extend(page_jobs)
            await sleep_with_jitter(min_delay, max_delay)

        return dedupe_jobs(jobs)
    finally:
        await context.close()
        await pw.stop()


async def collect_details(
    profile_dir: Path,
    jobs: list[dict[str, Any]],
    headless: bool,
    min_delay: float,
    max_delay: float,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    ensure_dir(profile_dir)
    selected = jobs[:limit] if limit is not None else jobs
    pw, context = await launch_context(profile_dir, headless=headless)
    try:
        page = await ensure_page(context)
        details: list[dict[str, Any]] = []
        total = len(selected)
        for idx, job in enumerate(selected, start=1):
            job_url = str(job.get("job_url", ""))
            if not job_url:
                continue
            print(f"[details] {idx}/{total} {job_url}")
            try:
                detail = await fetch_job_detail(page, job)
                details.append(detail)
            except Exception as exc:
                print(f"[warn] failed to fetch {job_url}: {exc}")
            await sleep_with_jitter(min_delay, max_delay)
        return details
    finally:
        await context.close()
        await pw.stop()


def default_output_path(prefix: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_DIR / f"{prefix}_{ts}.jsonl"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone LinkedIn Jobs Collector PoC")
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="Open browser and persist LinkedIn login session")
    login.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR)
    login.add_argument("--headless", action="store_true", help="Run browser in headless mode (usually keep false)")

    collect = sub.add_parser("collect", help="Collect job cards from LinkedIn search pages")
    collect.add_argument("--keywords", required=True)
    collect.add_argument("--location", default="")
    collect.add_argument("--pages", type=int, default=1)
    collect.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR)
    collect.add_argument("--headless", action="store_true")
    collect.add_argument("--min-delay", type=float, default=1.5)
    collect.add_argument("--max-delay", type=float, default=3.0)
    collect.add_argument("--output", type=Path, default=None)
    collect.add_argument("--with-details", action="store_true", help="Also open each job URL and collect JD details")
    collect.add_argument("--max-details", type=int, default=20)
    collect.add_argument("--details-output", type=Path, default=None)

    details = sub.add_parser("details", help="Collect detailed JD from URLs or previous jsonl")
    details.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR)
    details.add_argument("--headless", action="store_true")
    details.add_argument("--min-delay", type=float, default=1.5)
    details.add_argument("--max-delay", type=float, default=3.0)
    details.add_argument("--limit", type=int, default=None)
    details.add_argument("--input", type=Path, default=None, help="JSONL file from collect command")
    details.add_argument("--url", action="append", default=[], help="Job URL (repeatable)")
    details.add_argument("--output", type=Path, default=None)

    return parser.parse_args(argv)


async def run_command(args: argparse.Namespace) -> int:
    if args.command == "login":
        return await login_flow(profile_dir=args.profile_dir, headless=bool(args.headless))

    if args.command == "collect":
        if args.pages < 1:
            print("[error] --pages must be >= 1")
            return 2
        jobs = await collect_jobs(
            profile_dir=args.profile_dir,
            keywords=args.keywords,
            location=args.location,
            pages=args.pages,
            headless=bool(args.headless),
            min_delay=float(args.min_delay),
            max_delay=float(args.max_delay),
        )
        output = args.output or default_output_path("linkedin_jobs")
        write_jsonl(output, jobs)
        print(f"[ok] wrote {len(jobs)} job summaries -> {output}")

        if args.with_details:
            details = await collect_details(
                profile_dir=args.profile_dir,
                jobs=jobs,
                headless=bool(args.headless),
                min_delay=float(args.min_delay),
                max_delay=float(args.max_delay),
                limit=int(args.max_details),
            )
            details_output = args.details_output or default_output_path("linkedin_job_details")
            write_jsonl(details_output, details)
            print(f"[ok] wrote {len(details)} job details -> {details_output}")
        return 0

    if args.command == "details":
        jobs: list[dict[str, Any]] = []
        if args.input:
            jobs.extend(read_jsonl(args.input))
        for url in args.url:
            jobs.append(
                {"job_url": url, "job_id": extract_job_id(url), "source": "linkedin", "collected_at": utc_now_iso()}
            )

        jobs = dedupe_jobs(jobs)
        if not jobs:
            print("[error] provide --input JSONL and/or --url")
            return 2

        details = await collect_details(
            profile_dir=args.profile_dir,
            jobs=jobs,
            headless=bool(args.headless),
            min_delay=float(args.min_delay),
            max_delay=float(args.max_delay),
            limit=args.limit,
        )
        output = args.output or default_output_path("linkedin_job_details")
        write_jsonl(output, details)
        print(f"[ok] wrote {len(details)} job details -> {output}")
        return 0

    print(f"[error] unsupported command: {args.command}")
    return 2


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        return asyncio.run(run_command(args))
    except KeyboardInterrupt:
        print("\n[warn] interrupted by user")
        return 130
    except RuntimeError as exc:
        print(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
