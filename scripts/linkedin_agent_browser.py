#!/usr/bin/env python3
"""Deterministic LinkedIn collector using Vercel agent-browser CLI.

Collects `title`, `jd`, `link` in one run with pagination and randomized
intervals between page turns.
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from resume_agent.domain.linkedin_jobs import (
    build_search_url,
    check_login_required,
    parse_job_detail,
    parse_job_listings,
)

DEFAULT_CDP_PORT = 9222
DEFAULT_PROFILE = "~/.resume-agent/chrome-profile"
PAGE_SIZE = 25
JITTER_MIN_SECONDS = 0.7
JITTER_MAX_SECONDS = 1.9
JD_MAX_CHARS = 700


@dataclass
class JobRecord:
    title: str
    link: str
    jd: str
    company: str = ""
    location: str = ""
    job_id: str = ""
    posted_time: str = ""


def _compact(text: Any) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    # LinkedIn card text sometimes repeats exactly twice in extracted nodes.
    if value:
        half = len(value) // 2
        if len(value) % 2 == 0 and value[:half] == value[half:]:
            value = value[:half].strip()
    return value


def _jd_snippet(text: str) -> str:
    value = _compact(text)
    if len(value) <= JD_MAX_CHARS:
        return value
    return value[:JD_MAX_CHARS].rstrip() + "..."


def _job_id_from_url(url: str) -> str:
    match = re.search(r"/jobs/view/([0-9]+)", url or "")
    return match.group(1) if match else ""


class AgentBrowserRunner:
    def __init__(self, session: str, profile: str, cdp_port: int, headed: bool, use_cdp: bool):
        self.session = session
        self.profile = str(Path(profile).expanduser())
        self.cdp_port = cdp_port
        self.headed = headed
        self.use_cdp = use_cdp

    def _base_flags(self) -> list[str]:
        flags = ["--session", self.session]
        if self.use_cdp:
            flags.extend(["--cdp", str(self.cdp_port)])
        if self.profile:
            flags.extend(["--profile", self.profile])
        if self.headed:
            flags.append("--headed")
        return flags

    def run(
        self, *args: str, _retry_on_no_page: bool = True, _retry_on_context_destroyed: bool = True
    ) -> dict[str, Any]:
        cmd = ["agent-browser", *self._base_flags(), "--json", *args]
        proc = subprocess.run(cmd, text=True, capture_output=True)
        output = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            if _retry_on_no_page and "No page found" in (output + "\n" + err):
                # Some CDP-attached sessions start with no active tab.
                self.run("tab", "new", _retry_on_no_page=False, _retry_on_context_destroyed=False)
                return self.run(*args, _retry_on_no_page=False, _retry_on_context_destroyed=False)
            if _retry_on_context_destroyed and "Execution context was destroyed" in (output + "\n" + err):
                time.sleep(0.8)
                return self.run(*args, _retry_on_no_page=False, _retry_on_context_destroyed=False)
            detail = output or err or f"exit {proc.returncode}"
            raise RuntimeError(f"agent-browser failed: {' '.join(args)} | {detail}")

        # Parse last JSON line in stdout.
        payload: dict[str, Any] | None = None
        for line in reversed(output.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue

        if not payload:
            raise RuntimeError(f"agent-browser returned non-JSON output for: {' '.join(args)}")
        if not payload.get("success", False):
            error_text = str(payload.get("error", ""))
            if _retry_on_context_destroyed and "Execution context was destroyed" in error_text:
                time.sleep(0.8)
                return self.run(*args, _retry_on_no_page=False, _retry_on_context_destroyed=False)
            raise RuntimeError(f"agent-browser error on {' '.join(args)}: {payload.get('error')}")
        return payload.get("data", {})

    def eval(self, script: str) -> Any:
        data = self.run("eval", script)
        return data.get("result")


def _cdp_ready(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.2):
            return True
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False


def _launch_chrome(port: int, profile: str) -> None:
    profile_path = str(Path(profile).expanduser())
    system = platform.system()

    if system == "Darwin":
        subprocess.Popen(
            [
                "open",
                "-na",
                "Google Chrome",
                "--args",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile_path}",
                "--no-first-run",
                "--no-default-browser-check",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    chrome_paths = {
        "Linux": "google-chrome",
        "Windows": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    }
    chrome_bin = chrome_paths.get(system)
    if not chrome_bin:
        raise RuntimeError(f"Unsupported platform for auto-launch: {system}")
    subprocess.Popen(
        [
            chrome_bin,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_path}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _ensure_cdp(port: int, profile: str, auto_launch: bool) -> None:
    if _cdp_ready(port):
        return
    if not auto_launch:
        raise RuntimeError(f"CDP port {port} is not available. Start Chrome with --remote-debugging-port={port}.")
    _launch_chrome(port, profile)
    deadline = time.time() + 10
    while time.time() < deadline:
        if _cdp_ready(port):
            return
        time.sleep(0.5)
    raise RuntimeError(f"CDP port {port} did not become ready in time.")


def _extract_jobs_script() -> str:
    return r"""
(() => {
  const compact = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const normalizeUrl = (value) => {
    if (!value) return '';
    try { return String(value).split('?')[0]; } catch (e) { return String(value); }
  };
  const parseJobId = (url) => {
    const match = String(url || '').match(/\/jobs\/view\/([0-9]+)/);
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
    const key = jobId || url || `${title}|${company}|${location}`;
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push({ title, company, location, job_id: jobId, url, posted_time: postedTime });
  }
  return out;
})()
"""


def _click_next_script() -> str:
    return r"""
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


def _marker_script() -> str:
    return r"""
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


def _signature(jobs: list[dict[str, Any]]) -> str:
    top = jobs[:3]
    return "||".join(
        f"{job.get('job_id','')}|{job.get('url','')}|{job.get('title','')}|{job.get('company','')}|{job.get('location','')}"
        for job in top
    )


def _scroll_page(runner: AgentBrowserRunner) -> None:
    for _ in range(3):
        runner.eval("window.scrollBy(0, window.innerHeight)")
        time.sleep(1.0)
    runner.eval("window.scrollTo(0, 0)")


def _wait_for_page_change(runner: AgentBrowserRunner, prev_sig: str, prev_marker: str) -> bool:
    deadline = time.time() + 8.0
    while time.time() < deadline:
        time.sleep(0.5)
        jobs = runner.eval(_extract_jobs_script()) or []
        if isinstance(jobs, list):
            sig = _signature(jobs)
            if sig and sig != prev_sig:
                return True
        marker = _compact(runner.eval(_marker_script()))
        if marker and prev_marker and marker != prev_marker:
            return True
    return False


def _safe_jobs(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "title": _compact(item.get("title")),
                "company": _compact(item.get("company")),
                "location": _compact(item.get("location")),
                "job_id": _compact(item.get("job_id")),
                "url": _compact(item.get("url")),
                "posted_time": _compact(item.get("posted_time")),
            }
        )
    return out


def _jobs_from_text_fallback(text: str) -> list[dict[str, str]]:
    jobs = parse_job_listings(text)
    out: list[dict[str, str]] = []
    for item in jobs:
        out.append(
            {
                "title": _compact(item.title),
                "company": _compact(item.company),
                "location": _compact(item.location),
                "job_id": _compact(item.job_id),
                "url": _compact(item.url),
                "posted_time": _compact(item.posted_time),
            }
        )
    return out


def _collect_listings(
    runner: AgentBrowserRunner,
    keywords: str,
    location: str,
    limit: int,
    max_pages: int,
) -> list[dict[str, str]]:
    def open_with_retry(url: str, attempts: int = 3) -> None:
        last_error: Exception | None = None
        for i in range(attempts):
            try:
                runner.run("open", url)
                return
            except Exception as e:
                last_error = e
                # Fallback for flaky open/title read on heavy redirect pages.
                try:
                    runner.run("open", "about:blank")
                    runner.eval(f"window.location.href = {json.dumps(url)}")
                    runner.run("wait", "2200")
                    return
                except Exception:
                    pass
                if i < attempts - 1:
                    time.sleep(1.0 + i * 0.7)
        raise RuntimeError(str(last_error) if last_error else f"open failed for {url}")

    listings: list[dict[str, str]] = []
    seen: set[str] = set()

    open_with_retry(build_search_url(keywords, location, start=0))
    runner.run("wait", "1200")
    pages_budget = max(1, min(max_pages, ((limit + PAGE_SIZE - 1) // PAGE_SIZE) + 2))

    for page_idx in range(pages_budget):
        _scroll_page(runner)
        page_jobs = _safe_jobs(runner.eval(_extract_jobs_script()))
        if not page_jobs:
            main_text = _compact(
                runner.eval("document.querySelector('main')?.innerText || document.body?.innerText || ''")
            )
            page_jobs = _jobs_from_text_fallback(main_text)
        if not page_jobs:
            break

        for job in page_jobs:
            key = (
                job.get("job_id") or job.get("url") or f"{job.get('title')}|{job.get('company')}|{job.get('location')}"
            )
            if not key or key in seen:
                continue
            seen.add(key)
            listings.append(job)
            if len(listings) >= limit:
                return listings[:limit]

        prev_sig = _signature(page_jobs)
        prev_marker = _compact(runner.eval(_marker_script()))
        clicked = bool(runner.eval(_click_next_script()))
        if not clicked:
            break
        time.sleep(random.uniform(JITTER_MIN_SECONDS, JITTER_MAX_SECONDS))
        if not _wait_for_page_change(runner, prev_sig, prev_marker):
            # One fallback: URL offset pagination.
            fallback = build_search_url(keywords, location, start=(page_idx + 1) * PAGE_SIZE)
            open_with_retry(fallback)
            runner.run("wait", "1200")

    return listings[:limit]


def _collect_details(runner: AgentBrowserRunner, listings: list[dict[str, str]]) -> list[JobRecord]:
    results: list[JobRecord] = []
    for idx, item in enumerate(listings, start=1):
        url = item.get("url", "")
        title = item.get("title", "")
        if not url:
            job_id = item.get("job_id", "")
            url = f"https://www.linkedin.com/jobs/view/{job_id}/" if job_id else ""
        if not url:
            results.append(
                JobRecord(
                    title=title,
                    link="",
                    jd="",
                    company=item.get("company", ""),
                    location=item.get("location", ""),
                    job_id=item.get("job_id", ""),
                    posted_time=item.get("posted_time", ""),
                )
            )
            continue

        try:
            runner.run("open", url)
            text = _compact(runner.eval("document.querySelector('main')?.innerText || document.body?.innerText || ''"))
            detail = parse_job_detail(text)
            jd = _jd_snippet(detail.description or text)
            results.append(
                JobRecord(
                    title=title or _compact(detail.title),
                    link=url,
                    jd=jd,
                    company=item.get("company", "") or _compact(detail.company),
                    location=item.get("location", "") or _compact(detail.location),
                    job_id=item.get("job_id", "") or _job_id_from_url(url),
                    posted_time=item.get("posted_time", "") or _compact(detail.posted_time),
                )
            )
        except Exception:
            results.append(
                JobRecord(
                    title=title,
                    link=url,
                    jd="",
                    company=item.get("company", ""),
                    location=item.get("location", ""),
                    job_id=item.get("job_id", "") or _job_id_from_url(url),
                    posted_time=item.get("posted_time", ""),
                )
            )
        if idx < len(listings):
            time.sleep(random.uniform(0.2, 0.5))
    return results


def _keyword_variants(primary: str) -> list[str]:
    base = _compact(primary)
    variants: list[str] = [base]
    lowered = base.lower()
    if "front" in lowered:
        candidates = [
            "Frontend Engineer",
            "Frontend Developer",
            "前端工程师",
            "前端开发",
            "Web Developer",
        ]
        variants.extend(candidates)
    # Preserve order and remove duplicates.
    uniq: list[str] = []
    seen: set[str] = set()
    for item in variants:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        uniq.append(item.strip())
    return uniq


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LinkedIn collector via Vercel agent-browser CLI.")
    p.add_argument("--keywords", required=True, help='Search keywords, e.g. "Front Engineer"')
    p.add_argument("--location", default="", help='Location, e.g. "China"')
    p.add_argument("--limit", type=int, default=40, help="Jobs to collect (default: 40)")
    p.add_argument("--max-pages", type=int, default=8, help="Max paginated pages to scan (default: 8)")
    p.add_argument("--session", default="", help="agent-browser session name (default: auto-generated)")
    p.add_argument("--profile", default=DEFAULT_PROFILE, help="Chrome profile path")
    p.add_argument("--cdp-port", type=int, default=DEFAULT_CDP_PORT, help="CDP port (default: 9222)")
    p.add_argument(
        "--use-cdp", action="store_true", help="Attach to an existing Chrome via CDP instead of launching via profile"
    )
    p.add_argument("--headed", action="store_true", help="Show browser window")
    p.add_argument("--no-auto-launch", action="store_true", help="Disable auto-launch for CDP Chrome")
    p.add_argument(
        "--output",
        default="workspace/linkedin_poc/linkedin_jobs_agent_browser.json",
        help="Output JSON file",
    )
    p.add_argument("--keep-open", action="store_true", help="Do not close agent-browser session at end")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit < 1:
        print("limit must be >= 1", file=sys.stderr)
        return 2

    if args.use_cdp:
        _ensure_cdp(args.cdp_port, args.profile, auto_launch=not args.no_auto_launch)
    session_name = args.session or f"linkedin-agent-browser-{int(time.time())}"
    runner = AgentBrowserRunner(
        session=session_name,
        profile=args.profile,
        cdp_port=args.cdp_port,
        headed=args.headed,
        use_cdp=args.use_cdp,
    )

    def open_with_retry(url: str, attempts: int = 3) -> None:
        last_error: Exception | None = None
        for i in range(attempts):
            try:
                runner.run("open", url)
                return
            except Exception as e:
                last_error = e
                try:
                    runner.run("open", "about:blank")
                    runner.eval(f"window.location.href = {json.dumps(url)}")
                    runner.run("wait", "2200")
                    return
                except Exception:
                    pass
                if i < attempts - 1:
                    time.sleep(1.0 + i * 0.7)
        raise RuntimeError(str(last_error) if last_error else f"open failed for {url}")

    try:
        # Login preflight.
        open_with_retry("https://www.linkedin.com/feed/")
        feed_text = _compact(runner.eval("document.querySelector('main')?.innerText || document.body?.innerText || ''"))
        if check_login_required(feed_text):
            raise RuntimeError("LinkedIn login required in this profile. Please login once and re-run.")

        print(f"[1/3] Collect listings: keywords={args.keywords!r}, location={args.location!r}, limit={args.limit}")
        listings: list[dict[str, str]] = []
        seen: set[str] = set()
        for keyword in _keyword_variants(args.keywords):
            need = args.limit - len(listings)
            if need <= 0:
                break
            chunk = _collect_listings(runner, keyword, args.location, need, args.max_pages)
            for item in chunk:
                key = (
                    item.get("job_id")
                    or item.get("url")
                    or f"{item.get('title')}|{item.get('company')}|{item.get('location')}"
                )
                if not key or key in seen:
                    continue
                seen.add(key)
                listings.append(item)
                if len(listings) >= args.limit:
                    break
        print(f"[2/3] Listings collected: {len(listings)}")

        records = _collect_details(runner, listings)
        print(f"[3/3] Details collected: {len(records)}")

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "query": {"keywords": args.keywords, "location": args.location, "limit": args.limit},
            "count": len(records),
            "jobs": [asdict(item) for item in records],
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"saved: {output_path}")
        return 0
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        if not args.keep_open:
            try:
                runner.run("close")
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
