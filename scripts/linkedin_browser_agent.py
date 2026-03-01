#!/usr/bin/env python3
"""LinkedIn browser-agent style script for deterministic job collection.

Goal:
- One script run for: keyword/location search, pagination, and detail fetch
- Output structured records with: title, jd, link
- Avoid multi-step LLM orchestration overhead
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from math import ceil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from resume_agent.core.llm import load_raw_config
from resume_agent.domain.linkedin_jobs import (
    build_search_url,
    check_login_required,
    parse_job_detail,
)

DEFAULT_CHROME_PROFILE = "~/.resume-agent/chrome-profile"
DEFAULT_CDP_ENDPOINT = "http://127.0.0.1:9222"
PAGE_SIZE = 25
DEFAULT_WAIT_SECONDS = 1.0

CHROME_PATHS = {
    "Darwin": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "Linux": "google-chrome",
    "Windows": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
}


@dataclass
class JobRecord:
    title: str
    link: str
    jd: str
    company: str = ""
    location: str = ""
    job_id: str = ""
    posted_time: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministic LinkedIn browser agent script (title + jd + link).",
    )
    parser.add_argument("--keywords", required=True, help='Search keywords, e.g. "Front Engineer"')
    parser.add_argument("--location", default="", help='Location, e.g. "China"')
    parser.add_argument("--limit", type=int, default=40, help="Number of jobs to collect (default: 40)")
    parser.add_argument("--max-pages", type=int, default=8, help="Hard cap on searched pages (default: 8)")
    parser.add_argument("--detail-workers", type=int, default=2, help="Concurrent detail fetch workers (default: 2)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument(
        "--output",
        default="workspace/linkedin_jobs.json",
        help="Output JSON path (default: workspace/linkedin_jobs.json)",
    )
    parser.add_argument(
        "--config", default="config/config.local.yaml", help="Config path (default: config/config.local.yaml)"
    )
    parser.add_argument("--chrome-profile", default="", help="Override Chrome user-data-dir path")
    parser.add_argument("--cdp-endpoint", default="", help="Override CDP endpoint, e.g. http://127.0.0.1:9222")
    parser.add_argument("--channel", default="", help='Patchright channel, e.g. "chrome"')
    parser.add_argument("--executable-path", default="", help="Custom browser executable path")
    parser.add_argument(
        "--no-auto-launch",
        action="store_true",
        help="Disable auto-launch when cdp endpoint is unavailable",
    )
    return parser.parse_args()


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_job_id_from_url(url: str) -> str:
    match = re.search(r"/jobs/view/([0-9]+)", url or "")
    return match.group(1) if match else ""


class LinkedInBrowserAgentScript:
    def __init__(
        self,
        *,
        chrome_profile: str,
        cdp_endpoint: str,
        channel: str,
        executable_path: str,
        headless: bool,
        auto_launch: bool,
        detail_workers: int,
    ):
        self.chrome_profile = str(Path(chrome_profile).expanduser())
        self.cdp_endpoint = cdp_endpoint
        self.channel = channel
        self.executable_path = str(Path(executable_path).expanduser()) if executable_path else ""
        self.headless = headless
        self.auto_launch = auto_launch
        self.detail_workers = max(1, int(detail_workers))

        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._search_page: Any = None

    async def connect(self) -> None:
        from patchright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        if self.cdp_endpoint:
            self._context = await self._connect_over_cdp_with_optional_launch()
        else:
            launch_kwargs: dict[str, Any] = {
                "user_data_dir": self.chrome_profile,
                "headless": self.headless,
                "args": ["--no-first-run", "--no-default-browser-check"],
            }
            if self.channel:
                launch_kwargs["channel"] = self.channel
            if self.executable_path:
                launch_kwargs["executable_path"] = self.executable_path
            self._context = await self._playwright.chromium.launch_persistent_context(**launch_kwargs)

        self._search_page = self._context.pages[0] if self._context.pages else await self._context.new_page()

    async def _connect_over_cdp_with_optional_launch(self) -> Any:
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(endpoint_url=self.cdp_endpoint)
        except Exception as e:
            if not self.auto_launch:
                raise RuntimeError(
                    f"Cannot connect CDP endpoint {self.cdp_endpoint}. "
                    "Start Chrome with remote debugging or remove --no-auto-launch."
                ) from e
            self._launch_chrome_for_cdp()
            await asyncio.sleep(4.0)
            self._browser = await self._playwright.chromium.connect_over_cdp(endpoint_url=self.cdp_endpoint)

        return self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()

    def _launch_chrome_for_cdp(self) -> None:
        parsed = urlparse(self.cdp_endpoint)
        port = parsed.port or 9222
        system = platform.system()

        if system == "Darwin" and not self.executable_path:
            subprocess.Popen(
                [
                    "open",
                    "-na",
                    "Google Chrome",
                    "--args",
                    f"--remote-debugging-port={port}",
                    f"--user-data-dir={self.chrome_profile}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "about:blank",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return

        chrome_bin = self.executable_path or CHROME_PATHS.get(system)
        if not chrome_bin:
            raise RuntimeError(f"Unsupported platform for Chrome auto-launch: {system}")

        subprocess.Popen(
            [
                chrome_bin,
                f"--remote-debugging-port={port}",
                f"--user-data-dir={self.chrome_profile}",
                "--no-first-run",
                "--no-default-browser-check",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    async def ensure_logged_in(self) -> None:
        await self._search_page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=20000)
        try:
            await self._search_page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        text = await self._search_page.evaluate(
            "document.querySelector('main')?.innerText || document.body?.innerText || ''"
        )
        if check_login_required(str(text)):
            raise RuntimeError(
                "LinkedIn login required. Please sign in once in the launched browser/profile and run again."
            )

    async def collect_listings(self, keywords: str, location: str, limit: int, max_pages: int) -> list[dict[str, str]]:
        target_pages = max(1, min(max_pages, ceil(limit / PAGE_SIZE) + 2))
        search_url = build_search_url(keywords, location, start=0)
        await self._search_page.goto(search_url, wait_until="domcontentloaded", timeout=25000)

        all_jobs: list[dict[str, str]] = []
        seen: set[str] = set()

        for page_index in range(target_pages):
            await self._scroll_page()
            page_jobs = await self._extract_jobs_from_dom(self._search_page)
            for job in page_jobs:
                key = (
                    job.get("job_id")
                    or job.get("url")
                    or f"{job.get('title','')}|{job.get('company','')}|{job.get('location','')}"
                )
                if not key or key in seen:
                    continue
                seen.add(key)
                all_jobs.append(job)
                if len(all_jobs) >= limit:
                    return all_jobs[:limit]

            prev_sig = self._signature(page_jobs)
            prev_marker = await self._get_pagination_marker(self._search_page)
            clicked = await self._click_next_page(self._search_page)
            if not clicked:
                break

            changed = await self._wait_for_page_change(prev_sig, prev_marker)
            if not changed and page_index + 1 < target_pages:
                # Fallback once: offset URL mode.
                fallback_url = build_search_url(keywords, location, start=(page_index + 1) * PAGE_SIZE)
                await self._search_page.goto(fallback_url, wait_until="domcontentloaded", timeout=25000)

        return all_jobs[:limit]

    async def fetch_details(self, listings: list[dict[str, str]]) -> list[JobRecord]:
        semaphore = asyncio.Semaphore(self.detail_workers)

        async def worker(item: dict[str, str]) -> JobRecord:
            async with semaphore:
                page = await self._context.new_page()
                try:
                    url = normalize_text(item.get("url"))
                    if not url and item.get("job_id"):
                        url = f"https://www.linkedin.com/jobs/view/{item['job_id']}/"
                    if not url:
                        return JobRecord(
                            title=normalize_text(item.get("title")),
                            link="",
                            jd="",
                            company=normalize_text(item.get("company")),
                            location=normalize_text(item.get("location")),
                            job_id=normalize_text(item.get("job_id")),
                            posted_time=normalize_text(item.get("posted_time")),
                        )

                    await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                    text = await page.evaluate(
                        "document.querySelector('main')?.innerText || document.body?.innerText || ''"
                    )
                    detail = parse_job_detail(str(text))
                    jd = normalize_text(detail.description)
                    if not jd:
                        jd = normalize_text(text)[:1200]

                    return JobRecord(
                        title=normalize_text(item.get("title")) or normalize_text(detail.title),
                        link=url,
                        jd=jd,
                        company=normalize_text(item.get("company")) or normalize_text(detail.company),
                        location=normalize_text(item.get("location")) or normalize_text(detail.location),
                        job_id=normalize_text(item.get("job_id")) or parse_job_id_from_url(url),
                        posted_time=normalize_text(item.get("posted_time")) or normalize_text(detail.posted_time),
                    )
                except Exception:
                    return JobRecord(
                        title=normalize_text(item.get("title")),
                        link=normalize_text(item.get("url")),
                        jd="",
                        company=normalize_text(item.get("company")),
                        location=normalize_text(item.get("location")),
                        job_id=normalize_text(item.get("job_id"))
                        or parse_job_id_from_url(normalize_text(item.get("url"))),
                        posted_time=normalize_text(item.get("posted_time")),
                    )
                finally:
                    await page.close()

        return await asyncio.gather(*[worker(x) for x in listings])

    async def close(self) -> None:
        if self._search_page:
            try:
                await self._search_page.close()
            except Exception:
                pass
            self._search_page = None

        if self._context and not self.cdp_endpoint:
            await self._context.close()
        self._context = None

        if self._browser and not self.cdp_endpoint:
            await self._browser.close()
        self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def _scroll_page(self) -> None:
        for _ in range(3):
            await self._search_page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(DEFAULT_WAIT_SECONDS)
        await self._search_page.evaluate("window.scrollTo(0, 0)")

    @staticmethod
    async def _extract_jobs_from_dom(page: Any) -> list[dict[str, str]]:
        script = """
(() => {
  const compact = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const normalizeUrl = (value) => {
    if (!value) return '';
    try { return String(value).split('?')[0]; } catch (e) { return String(value); }
  };
  const parseJobId = (url) => {
    const match = String(url || '').match(/\\/jobs\\/view\\/([0-9]+)/);
    return match ? match[1] : '';
  };
  const cardSelectors = [
    'li.jobs-search-results__list-item',
    'li.scaffold-layout__list-item',
    'li[data-occludable-job-id]',
    'div.job-search-card',
  ];
  const cards = [];
  const nodeSeen = new Set();
  for (const sel of cardSelectors) {
    for (const node of document.querySelectorAll(sel)) {
      if (!node || nodeSeen.has(node)) continue;
      nodeSeen.add(node);
      cards.push(node);
    }
  }
  const out = [];
  const seen = new Set();
  for (const card of cards) {
    const link =
      card.querySelector('a[href*="/jobs/view/"]') ||
      card.querySelector('.job-card-list__title') ||
      card.querySelector('a');
    const url = normalizeUrl(link && link.href ? link.href : '');
    const jobId = parseJobId(url);
    const title = compact(
      (card.querySelector('a.job-card-list__title') && card.querySelector('a.job-card-list__title').textContent) ||
      (card.querySelector('.job-card-list__title') && card.querySelector('.job-card-list__title').textContent) ||
      (card.querySelector('h3.base-search-card__title') && card.querySelector('h3.base-search-card__title').textContent) ||
      (link && link.textContent) ||
      ''
    );
    const company = compact(
      (card.querySelector('h4.base-search-card__subtitle') && card.querySelector('h4.base-search-card__subtitle').textContent) ||
      (card.querySelector('.job-card-container__company-name') && card.querySelector('.job-card-container__company-name').textContent) ||
      (card.querySelector('.artdeco-entity-lockup__subtitle') && card.querySelector('.artdeco-entity-lockup__subtitle').textContent) ||
      ''
    );
    const location = compact(
      (card.querySelector('.job-search-card__location') && card.querySelector('.job-search-card__location').textContent) ||
      (card.querySelector('.job-card-container__metadata-item') && card.querySelector('.job-card-container__metadata-item').textContent) ||
      (card.querySelector('.artdeco-entity-lockup__caption') && card.querySelector('.artdeco-entity-lockup__caption').textContent) ||
      ''
    );
    const postedTime = compact(
      (card.querySelector('time') && card.querySelector('time').textContent) ||
      (card.querySelector('.job-search-card__listdate') && card.querySelector('.job-search-card__listdate').textContent) ||
      (card.querySelector('.job-search-card__listdate--new') && card.querySelector('.job-search-card__listdate--new').textContent) ||
      ''
    );
    if (!title && !company && !location) continue;
    const dedupeKey = jobId || url || `${title}|${company}|${location}`;
    if (!dedupeKey || seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);
    out.push({
      title,
      company,
      location,
      job_id: jobId,
      url,
      posted_time: postedTime
    });
  }
  return out;
})()
"""
        raw = await page.evaluate(script)
        if not isinstance(raw, list):
            return []
        jobs: list[dict[str, str]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            jobs.append(
                {
                    "title": normalize_text(item.get("title")),
                    "company": normalize_text(item.get("company")),
                    "location": normalize_text(item.get("location")),
                    "job_id": normalize_text(item.get("job_id")),
                    "url": normalize_text(item.get("url")),
                    "posted_time": normalize_text(item.get("posted_time")),
                }
            )
        return jobs

    @staticmethod
    def _signature(jobs: list[dict[str, str]]) -> str:
        if not jobs:
            return ""
        top = jobs[:3]
        return "||".join(
            f"{job.get('job_id')}|{job.get('url')}|{job.get('title')}|{job.get('company')}|{job.get('location')}"
            for job in top
        )

    @staticmethod
    async def _get_pagination_marker(page: Any) -> str:
        value = await page.evaluate(
            """
(() => {
  const markers = [
    '[aria-current="true"]',
    '.artdeco-pagination__indicator--number.active',
    '.jobs-search-pagination [aria-current="true"]',
  ];
  for (const sel of markers) {
    const el = document.querySelector(sel);
    if (!el) continue;
    const text = (el.textContent || '').trim();
    const aria = (el.getAttribute('aria-label') || '').trim();
    const value = text || aria;
    if (value) return value;
  }
  return '';
})()
"""
        )
        return normalize_text(value)

    async def _wait_for_page_change(self, previous_signature: str, previous_marker: str) -> bool:
        deadline = asyncio.get_event_loop().time() + 8.0
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.5)
            jobs = await self._extract_jobs_from_dom(self._search_page)
            signature = self._signature(jobs)
            if signature and signature != previous_signature:
                return True
            marker = await self._get_pagination_marker(self._search_page)
            if marker and previous_marker and marker != previous_marker:
                return True
        return False

    @staticmethod
    async def _click_next_page(page: Any) -> bool:
        result = await page.evaluate(
            """
(() => {
  const isDisabled = (el) => {
    if (!el) return true;
    const node = el.closest('button, a, li, div') || el;
    return (
      el.hasAttribute('disabled') ||
      el.getAttribute('aria-disabled') === 'true' ||
      el.classList.contains('disabled') ||
      el.classList.contains('artdeco-button--disabled') ||
      !!node.closest('[aria-disabled="true"], .disabled, .artdeco-button--disabled, li.disabled')
    );
  };
  const clickEl = (el) => {
    if (!el) return false;
    el.scrollIntoView({ block: 'center' });
    el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
    if (typeof el.click === 'function') el.click();
    return true;
  };
  const selectors = [
    'button[aria-label*="Next"]',
    'button[aria-label*="next"]',
    'button[aria-label*="next page"]',
    'button[aria-label*="下一"]',
    'button.jobs-search-pagination__button--next',
    'button.artdeco-pagination__button--next',
    '[data-test-pagination-next-btn]',
    'a[rel="next"]',
  ];
  const candidates = [];
  for (const sel of selectors) {
    for (const el of document.querySelectorAll(sel)) candidates.push(el);
  }
  for (const el of candidates) {
    if (isDisabled(el)) continue;
    if (clickEl(el)) return true;
  }
  return false;
})()
"""
        )
        return bool(result)


def load_linkedin_runtime_config(config_path: str) -> dict[str, Any]:
    cfg = load_raw_config(config_path)
    linkedin = cfg.get("linkedin", {}) if isinstance(cfg, dict) else {}
    patchright_cfg = linkedin.get("patchright", {}) if isinstance(linkedin, dict) else {}
    cdp_cfg = cfg.get("cdp", {}) if isinstance(cfg, dict) else {}

    chrome_profile = (
        patchright_cfg.get("chrome_profile")
        or linkedin.get("chrome_profile")
        or cdp_cfg.get("chrome_profile")
        or DEFAULT_CHROME_PROFILE
    )
    return {
        "chrome_profile": chrome_profile,
        "cdp_endpoint": patchright_cfg.get("cdp_endpoint", DEFAULT_CDP_ENDPOINT),
        "channel": patchright_cfg.get("channel", "chrome"),
        "executable_path": patchright_cfg.get("executable_path", ""),
        "auto_launch": patchright_cfg.get("auto_launch", True),
    }


async def main_async() -> int:
    args = parse_args()
    if args.limit < 1:
        print("limit must be >= 1", file=sys.stderr)
        return 2

    runtime = load_linkedin_runtime_config(args.config)
    chrome_profile = args.chrome_profile or runtime["chrome_profile"]
    cdp_endpoint = args.cdp_endpoint or runtime["cdp_endpoint"]
    channel = args.channel or runtime["channel"]
    executable_path = args.executable_path or runtime["executable_path"]
    auto_launch = False if args.no_auto_launch else bool(runtime["auto_launch"])

    agent = LinkedInBrowserAgentScript(
        chrome_profile=chrome_profile,
        cdp_endpoint=cdp_endpoint,
        channel=channel,
        executable_path=executable_path,
        headless=args.headless,
        auto_launch=auto_launch,
        detail_workers=args.detail_workers,
    )

    try:
        await agent.connect()
        await agent.ensure_logged_in()

        print(f"[1/3] searching jobs: keywords={args.keywords!r}, location={args.location!r}, limit={args.limit}")
        listings = await agent.collect_listings(args.keywords, args.location, args.limit, args.max_pages)
        print(f"[2/3] listings collected: {len(listings)}")

        records = await agent.fetch_details(listings[: args.limit])
        print(f"[3/3] details collected: {len(records)}")

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "query": {"keywords": args.keywords, "location": args.location, "limit": args.limit},
            "count": len(records),
            "jobs": [asdict(r) for r in records],
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"saved: {output_path}")
        return 0
    finally:
        await agent.close()


def main() -> int:
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        print("interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
