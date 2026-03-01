"""LinkedIn job search tools — browser automation adapters for LinkedIn workflows.

The default driver uses CDP against a locally running Chrome profile.
Optionally, a Patchright driver can be enabled for more resilient page
interaction on anti-bot-sensitive sites.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any, Dict, List, Protocol

from resume_agent.core.tools.base import BaseTool, ToolResult
from resume_agent.domain.linkedin_jobs import (
    JobListing,
    build_detail_url,
    build_search_url,
    check_login_required,
    format_job_detail,
    format_job_listings,
    parse_job_detail,
    parse_job_listings,
)
from resume_agent.tools.cdp_client import CDPClient
from resume_agent.tools.patchright_client import PatchrightClient

logger = logging.getLogger(__name__)

_DEFAULT_CDP_PORT = 9222
_DEFAULT_CHROME_PROFILE = "~/.resume-agent/chrome-profile"
_DEFAULT_DRIVER = "cdp"
_DEFAULT_PATCHRIGHT_CHANNEL = "chrome"
_LOGIN_CHECK_URL = "https://www.linkedin.com/feed/"
_LOGIN_ERROR = "LinkedIn login required. Please open the Chrome window, " "log into LinkedIn, then try again."
_PAGE_SIZE = 25  # LinkedIn results per page
_MAX_LIMIT = 100
_SCROLL_STEPS = 3
_SCROLL_DELAY_SECONDS = 1.0
_PAGE_CHANGE_TIMEOUT_SECONDS = 8.0
_PAGE_CHANGE_POLL_SECONDS = 0.5
_PAGE_JITTER_MIN_SECONDS = 0.6
_PAGE_JITTER_MAX_SECONDS = 1.8
_DEFAULT_DETAIL_WORKERS = 2
_DETAIL_WORKERS_MAX = 4
_DETAIL_JITTER_MIN_SECONDS = 0.15
_DETAIL_JITTER_MAX_SECONDS = 0.45
_JD_SNIPPET_MAX_CHARS = 480
_NEXT_PAGE_SELECTORS = [
    'button[aria-label*="Next"]',
    'button[aria-label*="next"]',
    'button[aria-label*="next page"]',
    'button[aria-label*="下一"]',
    "button.jobs-search-pagination__button--next",
    "button.artdeco-pagination__button--next",
    "[data-test-pagination-next-btn]",
    'a[rel="next"]',
]
_LINKEDIN_JOB_URL_RE = re.compile(
    r"^https?://(?:[\w-]+\.)?linkedin\.com/jobs/view/([0-9]+)(?:[/?].*)?$",
    flags=re.IGNORECASE,
)


class BrowserClient(Protocol):
    """Common client contract used by LinkedIn tools."""

    async def connect(self) -> None: ...

    async def navigate(self, url: str) -> None: ...

    async def evaluate(self, expression: str) -> Any: ...

    async def extract_main_text(self) -> str: ...

    async def close(self) -> None: ...


def _build_browser_client(
    driver: str,
    cdp_port: int,
    chrome_profile: str,
    auto_launch: bool,
    patchright_headless: bool,
    patchright_channel: str | None,
    patchright_executable_path: str | None,
    patchright_cdp_endpoint: str | None,
) -> BrowserClient:
    normalized_driver = str(driver or _DEFAULT_DRIVER).strip().lower()
    if normalized_driver == "cdp":
        return CDPClient(port=cdp_port, chrome_profile=chrome_profile, auto_launch=auto_launch)
    if normalized_driver in {"patchright", "playwright"}:
        return PatchrightClient(
            chrome_profile=chrome_profile,
            headless=patchright_headless,
            channel=patchright_channel,
            executable_path=patchright_executable_path,
            cdp_endpoint=patchright_cdp_endpoint,
            auto_launch=auto_launch,
        )
    raise ValueError(f"Unsupported linkedin driver: {driver}")


async def _preflight_login_check(client: BrowserClient) -> bool:
    """Navigate to LinkedIn feed and return True if login is required."""
    await client.navigate(_LOGIN_CHECK_URL)
    text = await client.extract_main_text()
    return check_login_required(text)


async def _safe_close_client(client: BrowserClient) -> None:
    """Best-effort browser cleanup that never raises."""
    try:
        await client.close()
    except Exception as e:
        logger.warning("LinkedIn browser cleanup failed: %s", e)


def _normalize_limit(limit: int) -> int:
    """Normalize result limit to a safe range."""
    if not isinstance(limit, int):
        raise ValueError("limit must be an integer")
    if limit < 1:
        raise ValueError("limit must be >= 1")
    return min(limit, _MAX_LIMIT)


def _job_dedupe_key(job: JobListing) -> str:
    """Build a stable dedupe key for merged job results."""
    return job.job_id or job.url or f"{job.title}|{job.company}|{job.location}"


def _page_signature(jobs: List[JobListing]) -> str:
    """Signature for change detection between pagination steps."""
    if not jobs:
        return ""
    top = jobs[:3]
    return "||".join(f"{j.job_id}|{j.url}|{j.title}|{j.company}|{j.location}" for j in top)


async def _scroll_results_page(client: BrowserClient) -> None:
    """Scroll search page to trigger lazy loading before extraction."""
    for _ in range(_SCROLL_STEPS):
        await client.evaluate("window.scrollBy(0, window.innerHeight)")
        await asyncio.sleep(_SCROLL_DELAY_SECONDS)
    await client.evaluate("window.scrollTo(0, 0)")


async def _extract_jobs_from_dom(client: BrowserClient) -> List[JobListing]:
    """Extract structured job cards from current LinkedIn search results page."""
    script = """
(() => {
  const compact = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const normalizeUrl = (value) => {
    if (!value) return '';
    try {
      return String(value).split('?')[0];
    } catch (e) {
      return String(value);
    }
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

  const results = [];
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

    results.push({
      title,
      company,
      location,
      job_id: jobId,
      url,
      posted_time: postedTime,
    });
  }

  return results;
})()
"""

    raw = await client.evaluate(script)
    if not isinstance(raw, list):
        return []

    jobs: List[JobListing] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        company = str(item.get("company", "")).strip()
        location = str(item.get("location", "")).strip()
        if not title and not company and not location:
            continue

        jobs.append(
            JobListing(
                title=title,
                company=company,
                location=location,
                job_id=str(item.get("job_id", "")).strip(),
                url=str(item.get("url", "")).strip(),
                posted_time=str(item.get("posted_time", "")).strip(),
            )
        )
    return jobs


async def _click_next_page(client: BrowserClient) -> Dict[str, Any]:
    """Click pagination control and return click status with diagnostic reason."""
    native_click = getattr(type(client), "click_first", None)
    if native_click is not None:
        try:
            clicked = await client.click_first(_NEXT_PAGE_SELECTORS)  # type: ignore[attr-defined]
            if clicked:
                return {"clicked": True, "reason": "clicked-next-native"}
        except Exception as e:
            logger.debug("Native click failed, fallback to DOM click script: %s", e)

    script = """
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
  const uniq = (list) => {
    const out = [];
    const seen = new Set();
    for (const el of list) {
      if (!el || seen.has(el)) continue;
      seen.add(el);
      out.push(el);
    }
    return out;
  };

  const selectors = %s;

  const candidates = [];
  for (const sel of selectors) {
    for (const el of document.querySelectorAll(sel)) candidates.push(el);
  }

  if (!candidates.length) {
    const controls = Array.from(document.querySelectorAll('button, a'));
    const fuzzy = controls.filter((el) => {
      const text = (el.textContent || '').trim().toLowerCase();
      const aria = (el.getAttribute('aria-label') || '').trim().toLowerCase();
      const rel = (el.getAttribute('rel') || '').trim().toLowerCase();
      return (
        rel === 'next' ||
        text === 'next' ||
        text.includes('next page') ||
        text.includes('show more jobs') ||
        text.includes('see more jobs') ||
        text.includes('more jobs') ||
        text.includes('下一页') ||
        text.includes('更多职位') ||
        text.includes('查看更多职位') ||
        aria.includes('next') ||
        aria.includes('next page') ||
        aria.includes('下一页')
      );
    });
    candidates.push(...fuzzy);
  }

  for (const el of uniq(candidates)) {
    if (isDisabled(el)) continue;
    if (clickEl(el)) return { clicked: true, reason: 'clicked-next' };
  }

  // Fallback: click the next numbered pagination button.
  const pageButtons = uniq(
    Array.from(document.querySelectorAll('button, a')).filter((el) => {
      const text = (el.textContent || '').trim();
      return /^[0-9]+$/.test(text);
    })
  );
  let activePage = null;
  for (const el of pageButtons) {
    if (el.getAttribute('aria-current') === 'true' || el.classList.contains('active')) {
      activePage = parseInt((el.textContent || '').trim(), 10);
      break;
    }
  }
  if (activePage !== null) {
    const nextPageButton = pageButtons.find((el) => {
      const n = parseInt((el.textContent || '').trim(), 10);
      return Number.isFinite(n) && n > activePage && !isDisabled(el);
    });
    if (nextPageButton && clickEl(nextPageButton)) {
      return { clicked: true, reason: 'clicked-number' };
    }
  }

  return { clicked: false, reason: candidates.length ? 'all-disabled' : 'not_found' };
})()
""" % str(_NEXT_PAGE_SELECTORS)

    result = await client.evaluate(script)
    if isinstance(result, dict):
        return {
            "clicked": bool(result.get("clicked", False)),
            "reason": str(result.get("reason", "")),
        }
    if isinstance(result, bool):
        return {"clicked": result, "reason": "bool-result"}
    return {"clicked": False, "reason": "invalid-result"}


async def _get_pagination_marker(client: BrowserClient) -> str:
    """Get current pagination marker (active page label) for change detection."""
    script = """
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
    value = await client.evaluate(script)
    return value.strip() if isinstance(value, str) else ""


async def _wait_for_page_change(client: BrowserClient, previous_signature: str, previous_marker: str = "") -> bool:
    """Wait until search results change after pagination click."""
    deadline = asyncio.get_event_loop().time() + _PAGE_CHANGE_TIMEOUT_SECONDS
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(_PAGE_CHANGE_POLL_SECONDS)
        jobs = await _extract_jobs_from_dom(client)
        signature = _page_signature(jobs)
        if signature and signature != previous_signature:
            return True
        marker = await _get_pagination_marker(client)
        if marker and previous_marker and marker != previous_marker:
            return True
    return False


async def _human_pagination_delay() -> None:
    """Insert a short random delay between pagination actions."""
    await asyncio.sleep(random.uniform(_PAGE_JITTER_MIN_SECONDS, _PAGE_JITTER_MAX_SECONDS))


def _normalize_jd_snippet(text: str) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= _JD_SNIPPET_MAX_CHARS:
        return compact
    return compact[:_JD_SNIPPET_MAX_CHARS].rstrip() + "..."


def _job_detail_url(job: JobListing) -> str:
    if job.url:
        return job.url
    if job.job_id:
        return build_detail_url(job.job_id)
    return ""


def _extract_job_id_from_url(job_url: str) -> str:
    """Extract LinkedIn numeric job ID from a full /jobs/view URL."""
    value = str(job_url or "").strip()
    if not value:
        return ""
    match = _LINKEDIN_JOB_URL_RE.match(value)
    if not match:
        return ""
    return str(match.group(1))


async def _fetch_job_jd_map(client: BrowserClient, jobs: List[JobListing], detail_workers: int) -> Dict[str, str]:
    """Fetch JD snippets for jobs, using parallel per-page fetch when available."""
    targets: List[tuple[str, str]] = []
    for job in jobs:
        key = _job_dedupe_key(job)
        url = _job_detail_url(job)
        if not key or not url:
            continue
        targets.append((key, url))

    if not targets:
        return {}

    workers = max(1, min(_DETAIL_WORKERS_MAX, detail_workers))
    jd_map: Dict[str, str] = {}

    has_page_api = all(
        hasattr(client, name) for name in ("new_page", "navigate_page", "extract_main_text_page", "close_page")
    )

    if has_page_api and workers > 1:
        sem = asyncio.Semaphore(workers)

        async def run_target(key: str, url: str) -> tuple[str, str]:
            async with sem:
                page = await client.new_page()  # type: ignore[attr-defined]
                try:
                    await client.navigate_page(page, url)  # type: ignore[attr-defined]
                    text = await client.extract_main_text_page(page)  # type: ignore[attr-defined]
                    detail = parse_job_detail(text)
                    snippet = _normalize_jd_snippet(detail.description or text)
                except Exception:
                    snippet = ""
                finally:
                    await client.close_page(page)  # type: ignore[attr-defined]
                await asyncio.sleep(random.uniform(_DETAIL_JITTER_MIN_SECONDS, _DETAIL_JITTER_MAX_SECONDS))
                return key, snippet

        pairs = await asyncio.gather(*[run_target(key, url) for key, url in targets])
        for key, snippet in pairs:
            if snippet:
                jd_map[key] = snippet
        return jd_map

    # Fallback: serialize on the active page.
    for key, url in targets:
        try:
            await client.navigate(url)
            text = await client.extract_main_text()
            detail = parse_job_detail(text)
            snippet = _normalize_jd_snippet(detail.description or text)
            if snippet:
                jd_map[key] = snippet
        except Exception:
            pass
        await asyncio.sleep(random.uniform(_DETAIL_JITTER_MIN_SECONDS, _DETAIL_JITTER_MAX_SECONDS))

    return jd_map


def _format_job_listings_with_jd(jobs: List[JobListing], jd_map: Dict[str, str]) -> str:
    """Format listings with JD snippets for one-shot consumption."""
    if not jobs:
        return "No jobs found."
    lines: List[str] = [f"Found {len(jobs)} jobs:"]
    for index, job in enumerate(jobs, start=1):
        lines.append(f"{index}. {job.title} — {job.company} ({job.location})")
        lines.append(f"   Link: {job.url or (_job_detail_url(job) or 'N/A')}")
        snippet = jd_map.get(_job_dedupe_key(job), "")
        if snippet:
            lines.append(f"   JD: {snippet}")
    return "\n".join(lines)


class JobSearchTool(BaseTool):
    """Search LinkedIn jobs by keywords and location."""

    name = "job_search"
    description = (
        "Search LinkedIn job listings by keywords and optional location only. "
        "Use this for role discovery (e.g., title/location searches), not for a specific job URL. "
        "Automatically paginates to collect the requested number of results. "
        "Can include per-job JD snippets in the same call via include_jd."
    )
    parameters: Dict[str, Any] = {
        "keywords": {
            "type": "string",
            "description": "Job search keywords (e.g. 'Senior Software Engineer')",
            "required": True,
        },
        "location": {
            "type": "string",
            "description": "Location filter (e.g. 'San Francisco, CA')",
        },
        "limit": {
            "type": "integer",
            "description": "Number of results to return. Automatically paginates if > 25. Default 25.",
            "default": 25,
        },
        "include_jd": {
            "type": "boolean",
            "description": "If true, fetch each result's JD snippet in the same call.",
        },
        "detail_workers": {
            "type": "integer",
            "description": "Parallel workers for JD fetching when driver supports multi-page fetch. Default 2.",
            "default": 2,
        },
    }

    def __init__(
        self,
        cdp_port: int = _DEFAULT_CDP_PORT,
        chrome_profile: str = _DEFAULT_CHROME_PROFILE,
        auto_launch: bool = True,
        driver: str = _DEFAULT_DRIVER,
        patchright_headless: bool = False,
        patchright_channel: str | None = _DEFAULT_PATCHRIGHT_CHANNEL,
        patchright_executable_path: str | None = None,
        patchright_cdp_endpoint: str | None = None,
    ):
        self.cdp_port = cdp_port
        self.chrome_profile = chrome_profile
        self.auto_launch = auto_launch
        self.driver = driver
        self.patchright_headless = patchright_headless
        self.patchright_channel = patchright_channel
        self.patchright_executable_path = patchright_executable_path
        self.patchright_cdp_endpoint = patchright_cdp_endpoint

    async def execute(
        self,
        keywords: str = "",
        location: str = "",
        limit: int = 25,
        include_jd: bool | None = None,
        detail_workers: int = _DEFAULT_DETAIL_WORKERS,
    ) -> ToolResult:
        if not keywords or not keywords.strip():
            return ToolResult(success=False, output="", error="Missing required parameter: keywords")
        try:
            normalized_limit = _normalize_limit(limit)
        except ValueError as e:
            return ToolResult(success=False, output="", error=str(e))
        if not isinstance(detail_workers, int) or detail_workers < 1:
            return ToolResult(success=False, output="", error="detail_workers must be a positive integer")

        try:
            client = _build_browser_client(
                driver=self.driver,
                cdp_port=self.cdp_port,
                chrome_profile=self.chrome_profile,
                auto_launch=self.auto_launch,
                patchright_headless=self.patchright_headless,
                patchright_channel=self.patchright_channel,
                patchright_executable_path=self.patchright_executable_path,
                patchright_cdp_endpoint=self.patchright_cdp_endpoint,
            )
        except ValueError as e:
            return ToolResult(success=False, output="", error=str(e))

        try:
            await client.connect()

            if await _preflight_login_check(client):
                return ToolResult(success=False, output="", error=_LOGIN_ERROR)

            all_jobs: List[JobListing] = []
            seen_keys: set[str] = set()
            pages_budget = max(1, (normalized_limit + _PAGE_SIZE - 1) // _PAGE_SIZE)
            use_url_pagination_fallback = False
            pagination_mode = "click"
            pages_collected = 0
            dom_extraction_used = False
            text_fallback_used = False
            last_click_reason = ""
            normalized_driver = str(self.driver or "").strip().lower()
            include_jd_effective = (
                normalized_driver in {"patchright", "playwright"} if include_jd is None else bool(include_jd)
            )

            # Open search once; prefer in-page pagination clicks afterwards.
            start_url = build_search_url(keywords.strip(), location.strip(), start=0)
            await client.navigate(start_url)

            for page in range(pages_budget):
                if page > 0 and use_url_pagination_fallback:
                    fallback_url = build_search_url(keywords.strip(), location.strip(), start=page * _PAGE_SIZE)
                    await client.navigate(fallback_url)
                    pagination_mode = "url_fallback"

                await _scroll_results_page(client)

                page_jobs = await _extract_jobs_from_dom(client)
                if page_jobs:
                    dom_extraction_used = True
                if not page_jobs:
                    # Fallback for layout changes where card extraction fails.
                    text = await client.extract_main_text()
                    page_jobs = parse_job_listings(text)
                    if page_jobs:
                        text_fallback_used = True

                if not page_jobs:
                    break

                pages_collected += 1
                for job in page_jobs:
                    key = _job_dedupe_key(job)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    all_jobs.append(job)
                    if len(all_jobs) >= normalized_limit:
                        break

                if len(all_jobs) >= normalized_limit:
                    break

                if use_url_pagination_fallback:
                    continue

                # Prefer click-based pagination; fallback to URL offsets if click is unavailable.
                prev_signature = _page_signature(page_jobs)
                prev_marker = await _get_pagination_marker(client)
                click_result = await _click_next_page(client)
                clicked = bool(click_result.get("clicked", False))
                last_click_reason = str(click_result.get("reason", ""))
                if not clicked:
                    use_url_pagination_fallback = True
                    continue
                await _human_pagination_delay()
                if not await _wait_for_page_change(client, prev_signature, prev_marker):
                    last_click_reason = "clicked-but-no-page-change"
                    use_url_pagination_fallback = True

            all_jobs = all_jobs[:normalized_limit]

            jd_map: Dict[str, str] = {}
            if include_jd_effective and all_jobs:
                jd_map = await _fetch_job_jd_map(client, all_jobs, detail_workers=detail_workers)

            output = _format_job_listings_with_jd(all_jobs, jd_map) if jd_map else format_job_listings(all_jobs)
            return ToolResult(
                success=True,
                output=output,
                data={
                    "jobs": [
                        {
                            "title": j.title,
                            "company": j.company,
                            "location": j.location,
                            "job_id": j.job_id,
                            "url": j.url,
                            "posted_time": j.posted_time,
                            "jd": jd_map.get(_job_dedupe_key(j), ""),
                        }
                        for j in all_jobs
                    ],
                    "total": len(all_jobs),
                    "driver": self.driver,
                    "include_jd": include_jd_effective,
                    "detail_workers": max(1, min(_DETAIL_WORKERS_MAX, detail_workers)),
                    "pagination_mode": pagination_mode,
                    "pages_collected": pages_collected,
                    "dom_extraction_used": dom_extraction_used,
                    "text_fallback_used": text_fallback_used,
                    "last_click_reason": last_click_reason,
                },
            )
        except ConnectionError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Cannot connect to Chrome: {e}",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Job search failed: {e}")
        finally:
            await _safe_close_client(client)


class JobDetailTool(BaseTool):
    """Get full details of a LinkedIn job posting."""

    name = "job_detail"
    description = (
        "Get full details of one LinkedIn job posting from an explicit LinkedIn job URL. "
        "Use only when the input already provides a concrete https://www.linkedin.com/jobs/view/<id>/ URL. "
        "Not for broad title/location search."
    )
    parameters: Dict[str, Any] = {
        "job_url": {
            "type": "string",
            "description": "Full LinkedIn job URL, e.g. https://www.linkedin.com/jobs/view/4353119521/",
            "required": True,
        },
    }

    def __init__(
        self,
        cdp_port: int = _DEFAULT_CDP_PORT,
        chrome_profile: str = _DEFAULT_CHROME_PROFILE,
        auto_launch: bool = True,
        driver: str = _DEFAULT_DRIVER,
        patchright_headless: bool = False,
        patchright_channel: str | None = _DEFAULT_PATCHRIGHT_CHANNEL,
        patchright_executable_path: str | None = None,
        patchright_cdp_endpoint: str | None = None,
    ):
        self.cdp_port = cdp_port
        self.chrome_profile = chrome_profile
        self.auto_launch = auto_launch
        self.driver = driver
        self.patchright_headless = patchright_headless
        self.patchright_channel = patchright_channel
        self.patchright_executable_path = patchright_executable_path
        self.patchright_cdp_endpoint = patchright_cdp_endpoint

    async def execute(self, job_url: str = "") -> ToolResult:
        normalized_url = str(job_url or "").strip()
        if not normalized_url:
            return ToolResult(success=False, output="", error="Missing required parameter: job_url")

        job_id = _extract_job_id_from_url(normalized_url)
        if not job_id:
            return ToolResult(
                success=False,
                output="",
                error=(
                    "Invalid job_url. Expected LinkedIn job URL like " "https://www.linkedin.com/jobs/view/<job_id>/"
                ),
            )

        try:
            client = _build_browser_client(
                driver=self.driver,
                cdp_port=self.cdp_port,
                chrome_profile=self.chrome_profile,
                auto_launch=self.auto_launch,
                patchright_headless=self.patchright_headless,
                patchright_channel=self.patchright_channel,
                patchright_executable_path=self.patchright_executable_path,
                patchright_cdp_endpoint=self.patchright_cdp_endpoint,
            )
        except ValueError as e:
            return ToolResult(success=False, output="", error=str(e))

        try:
            await client.connect()

            if await _preflight_login_check(client):
                return ToolResult(success=False, output="", error=_LOGIN_ERROR)

            url = build_detail_url(job_id)
            await client.navigate(url)
            text = await client.extract_main_text()
            detail = parse_job_detail(text)
            detail.url = url

            output = format_job_detail(detail)
            return ToolResult(
                success=True,
                output=output,
                data={
                    "driver": self.driver,
                    "title": detail.title,
                    "company": detail.company,
                    "location": detail.location,
                    "description": detail.description,
                    "url": detail.url,
                    "posted_time": detail.posted_time,
                    "seniority_level": detail.seniority_level,
                    "employment_type": detail.employment_type,
                },
            )
        except ConnectionError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Cannot connect to Chrome: {e}",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Job detail fetch failed: {e}")
        finally:
            await _safe_close_client(client)
