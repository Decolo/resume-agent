"""LinkedIn job search tools — browser automation via CDP against a local Chrome profile."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Dict, List, Optional, Protocol

from resume_agent.core.tools.base import BaseTool, ToolResult
from resume_agent.domain.linkedin_jobs import (
    JobListing,
    build_search_url,
    check_login_required,
    format_job_listings,
)
from resume_agent.tools.cdp_client import CDPClient

logger = logging.getLogger(__name__)

_DEFAULT_CDP_PORT = 9222
_DEFAULT_CHROME_PROFILE = "~/.resume-agent/chrome-profile"
_LOGIN_CHECK_URL = "https://www.linkedin.com/feed/"
_LOGIN_ERROR = "LinkedIn login required. Please open the Chrome window, " "log into LinkedIn, then try again."
_PAGE_SIZE = 25  # LinkedIn results per page
_MAX_LIMIT = 100
_JD_SNIPPET_MAX_CHARS = 480
_NEXT_KEYWORDS = {"next", "next page", "下一页", "下一", "show more", "more jobs", "更多职位"}
_LLM_PAGINATION_MODEL = "gemini-2.5-flash"
_PAGE_JITTER_MIN_SECONDS = 0.6
_PAGE_JITTER_MAX_SECONDS = 1.8
# --- New constants ---
_SCROLL_STEP_PX = 400
_SCROLL_JITTER = (0.5, 1.0)
_MAX_SCROLL_ITERATIONS = 40
_RIGHT_PANE_TIMEOUT = 6.0
_RIGHT_PANE_POLL = 0.4
_CARD_CLICK_JITTER = (0.3, 0.8)
_PAGE_CHANGE_TIMEOUT = 8.0
_PAGE_CHANGE_POLL = 0.5


class BrowserClient(Protocol):
    """Common client contract used by LinkedIn tools."""

    async def connect(self) -> None: ...

    async def navigate(self, url: str) -> None: ...

    async def evaluate(self, expression: str) -> Any: ...

    async def extract_main_text(self) -> str: ...

    async def close(self) -> None: ...


def _build_browser_client(
    cdp_port: int,
    chrome_profile: str,
    auto_launch: bool,
) -> BrowserClient:
    return CDPClient(
        port=cdp_port,
        chrome_profile=chrome_profile,
        auto_launch=auto_launch,
    )


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


def _job_dedupe_key(job: dict | JobListing) -> str:
    """Build a stable dedupe key for merged job results."""
    if isinstance(job, dict):
        return (
            job.get("jobId")
            or job.get("job_id")
            or job.get("url")
            or (f"{job.get('title', '')}|{job.get('company', '')}|{job.get('location', '')}")
        )
    return job.job_id or job.url or f"{job.title}|{job.company}|{job.location}"


def _normalize_jd_snippet(text: str) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= _JD_SNIPPET_MAX_CHARS:
        return compact
    return compact[:_JD_SNIPPET_MAX_CHARS].rstrip() + "..."


async def _human_pagination_delay() -> None:
    """Insert a short random delay between pagination actions."""
    await asyncio.sleep(random.uniform(_PAGE_JITTER_MIN_SECONDS, _PAGE_JITTER_MAX_SECONDS))


# ---------------------------------------------------------------------------
# New scroll + card + right-pane functions
# ---------------------------------------------------------------------------


async def _find_scroll_container(client: BrowserClient, retries: int = 5, poll: float = 1.0) -> Optional[str]:
    """Find the scrollable left-column container and tag it for later reference.

    Retries a few times because LinkedIn renders the job list asynchronously
    after the initial page load completes.
    """
    script = """
(() => {
  const selectors = [
    '.jobs-search-results-list',
    '.scaffold-layout__list > div',
    '.scaffold-layout__list',
    '.jobs-search-two-pane__results',
  ];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && el.scrollHeight > el.clientHeight) {
      el.setAttribute('data-ra-scroll', '1');
      return sel;
    }
  }
  // Walk up from first job card to find scrollable ancestor
  const card = document.querySelector(
    'li.jobs-search-results__list-item, li.scaffold-layout__list-item, ' +
    'li[data-occludable-job-id], div.job-search-card'
  );
  if (card) {
    let node = card.parentElement;
    while (node && node !== document.body) {
      if (node.scrollHeight > node.clientHeight) {
        node.setAttribute('data-ra-scroll', '1');
        return '[data-ra-scroll="1"]';
      }
      node = node.parentElement;
    }
  }
  return null;
})()
"""
    result = await client.evaluate(script)
    if isinstance(result, str):
        return result
    # Retry — LinkedIn renders job list asynchronously
    for _ in range(retries):
        await asyncio.sleep(poll)
        result = await client.evaluate(script)
        if isinstance(result, str):
            return result
    return None


async def _scroll_and_collect_cards(client: BrowserClient, container_sel: str) -> List[dict]:
    """Scroll the left column to bottom, collecting visible card metadata."""
    script_template = """
(() => {
  const container = document.querySelector('%s');
  if (!container) return { cards: [], atBottom: true };

  const compact = (v) => (v || '').replace(/\\s+/g, ' ').trim();
  const normalizeUrl = (v) => {
    if (!v) return '';
    try { return String(v).split('?')[0]; } catch(e) { return String(v); }
  };
  const parseJobId = (url) => {
    const m = String(url || '').match(/\\/jobs\\/view\\/([0-9]+)/);
    return m ? m[1] : '';
  };

  const cardSelectors = [
    'li.jobs-search-results__list-item',
    'li.scaffold-layout__list-item',
    'li[data-occludable-job-id]',
    'div.job-search-card',
  ];

  const seen = new Set();
  const results = [];
  for (const sel of cardSelectors) {
    for (const card of container.querySelectorAll(sel)) {
      if (seen.has(card)) continue;
      seen.add(card);

      const link = card.querySelector('a[href*="/jobs/view/"]')
        || card.querySelector('.job-card-list__title')
        || card.querySelector('a');
      const url = normalizeUrl(link && link.href ? link.href : '');
      const jobId = card.getAttribute('data-occludable-job-id') || parseJobId(url);

      const title = compact(
        (card.querySelector('.job-card-list__title') || {}).textContent
        || (card.querySelector('h3.base-search-card__title') || {}).textContent
        || (link || {}).textContent || ''
      );
      const company = compact(
        (card.querySelector('h4.base-search-card__subtitle') || {}).textContent
        || (card.querySelector('.job-card-container__company-name') || {}).textContent
        || ''
      );
      const location = compact(
        (card.querySelector('.job-search-card__location') || {}).textContent
        || (card.querySelector('.job-card-container__metadata-item') || {}).textContent
        || ''
      );
      const postedTime = compact(
        (card.querySelector('time') || {}).textContent
        || (card.querySelector('.job-search-card__listdate') || {}).textContent
        || ''
      );

      if (!title && !company && !location) continue;
      const key = jobId || url || (title + '|' + company + '|' + location);
      if (seen.has(key)) continue;
      seen.add(key);

      results.push({ title, company, location, jobId, url, postedTime });
    }
  }

  const atBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 5;
  return { cards: results, atBottom, scrollHeight: container.scrollHeight };
})()
"""

    all_cards: List[dict] = []
    seen_keys: set[str] = set()
    prev_scroll_height = 0
    stall_count = 0

    for _ in range(_MAX_SCROLL_ITERATIONS):
        # Scroll down
        await client.evaluate(f"document.querySelector('{container_sel}').scrollBy(0, {_SCROLL_STEP_PX})")
        await asyncio.sleep(random.uniform(*_SCROLL_JITTER))

        # Collect cards
        result = await client.evaluate(script_template % container_sel)
        if not isinstance(result, dict):
            break

        for card in result.get("cards", []):
            key = _job_dedupe_key(card)
            if key not in seen_keys:
                seen_keys.add(key)
                all_cards.append(card)

        if result.get("atBottom"):
            break

        # Stall detection
        sh = result.get("scrollHeight", 0)
        if sh == prev_scroll_height:
            stall_count += 1
            if stall_count >= 2:
                break
        else:
            stall_count = 0
        prev_scroll_height = sh

    return all_cards


async def _wait_for_right_pane(client: BrowserClient, expected_id: str, timeout: float = _RIGHT_PANE_TIMEOUT) -> bool:
    """Poll right pane until it shows content matching expected_id or has a non-empty title."""
    script = """
(() => {
  const paneSelectors = [
    '.jobs-search__job-details',
    '.scaffold-layout__detail',
    '.job-details-jobs-unified-top-card__container',
    '.jobs-details__main-content',
  ];
  for (const sel of paneSelectors) {
    const pane = document.querySelector(sel);
    if (!pane) continue;
    const links = pane.querySelectorAll('a[href*="/jobs/view/"]');
    for (const a of links) {
      if (a.href && a.href.includes('%s')) return true;
    }
    const title = pane.querySelector(
      '.job-details-jobs-unified-top-card__job-title, h1, h2.t-24'
    );
    if (title && (title.textContent || '').trim()) return true;
  }
  return false;
})()
"""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        ready = await client.evaluate(script % expected_id)
        if ready:
            return True
        await asyncio.sleep(_RIGHT_PANE_POLL)
    return False


async def _extract_from_right_pane(client: BrowserClient, include_jd: bool) -> Optional[dict]:
    """Extract job details from the right pane of the two-pane search layout."""
    jd_part = (
        """
    const jdEl = pane.querySelector('.jobs-description__content')
      || pane.querySelector('.jobs-description-content__text')
      || pane.querySelector('#job-details');
    result.jd = jdEl ? compact(jdEl.innerText || '') : '';
"""
        if include_jd
        else ""
    )

    script = (
        """
(() => {
  const compact = (v) => (v || '').replace(/\\s+/g, ' ').trim();
  const normalizeUrl = (v) => {
    if (!v) return '';
    try { return String(v).split('?')[0]; } catch(e) { return String(v); }
  };
  const paneSelectors = [
    '.jobs-search__job-details',
    '.scaffold-layout__detail',
    '.job-details-jobs-unified-top-card__container',
    '.jobs-details__main-content',
  ];
  for (const sel of paneSelectors) {
    const pane = document.querySelector(sel);
    if (!pane) continue;

    const titleEl = pane.querySelector('.job-details-jobs-unified-top-card__job-title')
      || pane.querySelector('h1')
      || pane.querySelector('h2.t-24');
    const title = titleEl ? compact(titleEl.textContent) : '';
    if (!title) continue;

    const companyEl = pane.querySelector('.job-details-jobs-unified-top-card__company-name');
    const company = companyEl ? compact(companyEl.textContent) : '';

    const locEl = pane.querySelector('.job-details-jobs-unified-top-card__bullet');
    const location = locEl ? compact(locEl.textContent) : '';

    const timeEl = pane.querySelector('.tvm__text--low-emphasis') || pane.querySelector('time');
    const postedTime = timeEl ? compact(timeEl.textContent) : '';

    const linkEl = pane.querySelector('a[href*="/jobs/view/"]');
    const url = normalizeUrl(linkEl ? linkEl.href : '');
    const jobIdMatch = String(url).match(/\\/jobs\\/view\\/([0-9]+)/);
    const jobId = jobIdMatch ? jobIdMatch[1] : '';

    const result = { title, company, location, postedTime, url, jobId };
    %s
    return result;
  }
  return null;
})()
"""
        % jd_part
    )

    result = await client.evaluate(script)
    return result if isinstance(result, dict) else None


async def _click_card_and_extract(client: BrowserClient, card_index: int, include_jd: bool) -> Optional[dict]:
    """Click card at index N, wait for right pane, extract details."""
    # Click the card (scroll into view + dispatch click)
    click_script = (
        """
(() => {
  const selectors = [
    'li.jobs-search-results__list-item',
    'li.scaffold-layout__list-item',
    'li[data-occludable-job-id]',
    'div.job-search-card',
  ];
  const cards = [];
  const seen = new Set();
  for (const sel of selectors) {
    for (const node of document.querySelectorAll(sel)) {
      if (seen.has(node)) continue;
      seen.add(node);
      cards.push(node);
    }
  }
  const card = cards[%d];
  if (!card) return { clicked: false };
  const link = card.querySelector('a[href*="/jobs/view/"]') || card.querySelector('a');
  const target = link || card;
  target.scrollIntoView({ block: 'center' });
  target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
  if (typeof target.click === 'function') target.click();
  const jobId = card.getAttribute('data-occludable-job-id') || '';
  const url = (link && link.href) ? String(link.href).split('?')[0] : '';
  const idMatch = url.match(/\\/jobs\\/view\\/([0-9]+)/);
  return { clicked: true, jobId: jobId || (idMatch ? idMatch[1] : '') };
})()
"""
        % card_index
    )

    click_result = await client.evaluate(click_script)
    if not isinstance(click_result, dict) or not click_result.get("clicked"):
        return None

    expected_id = str(click_result.get("jobId", ""))
    await _wait_for_right_pane(client, expected_id)
    return await _extract_from_right_pane(client, include_jd)


def _is_disabled_ax(node: dict) -> bool:
    """Check if an AX tree node is disabled."""
    for prop in node.get("properties", []):
        name = (prop.get("name", "") or "").lower()
        if name == "disabled":
            val = prop.get("value", {})
            if isinstance(val, dict):
                return bool(val.get("value", False))
            return bool(val)
    return False


async def _find_next_button_ax(client: BrowserClient) -> Optional[int]:
    """Search AX tree for pagination Next button. Returns backendDOMNodeId."""
    if not hasattr(client, "get_ax_tree"):
        return None
    nodes = await client.get_ax_tree()
    for node in nodes:
        role = (node.get("role", {}).get("value", "") or "").lower()
        name = (node.get("name", {}).get("value", "") or "").lower().strip()
        if role not in ("button", "link"):
            continue
        if _is_disabled_ax(node):
            continue
        if any(kw in name for kw in _NEXT_KEYWORDS):
            return node.get("backendDOMNodeId")
    return None


async def _find_next_button_llm(client: BrowserClient, api_key: str) -> Optional[int]:
    """Ask gemini-2.5-flash to identify Next button from interactive elements.

    Collects all buttons/links with text and aria-labels via JS, sends them
    to the LLM, and returns the backendDOMNodeId of the matched element.
    """
    # 1. Collect interactive elements with their text/aria-label
    collect_script = """
(() => {
  const els = Array.from(document.querySelectorAll('button, a'));
  return els.map((el, i) => ({
    index: i,
    tag: el.tagName.toLowerCase(),
    text: (el.textContent || '').trim().substring(0, 80),
    ariaLabel: (el.getAttribute('aria-label') || '').trim().substring(0, 80),
    disabled: el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true',
  })).filter(e => e.text || e.ariaLabel);
})()
"""
    elements = await client.evaluate(collect_script)
    if not isinstance(elements, list) or not elements:
        return None

    # 2. Ask LLM to identify the pagination Next button
    prompt = (
        "Below is a list of interactive elements (buttons and links) from a LinkedIn job search page.\n"
        "Which element is the pagination 'Next' button for going to the next page of results?\n"
        'Return ONLY valid JSON: {"index": N} where N is the element index, '
        'or {"found": false} if none is the Next button.\n\n'
    )
    for el in elements:
        prompt += f"[{el['index']}] <{el['tag']}> text=\"{el['text']}\" aria-label=\"{el['ariaLabel']}\" disabled={el['disabled']}\n"

    try:
        import json as _json

        from google import genai
        from google.genai import types

        llm_client = genai.Client(api_key=api_key)
        import asyncio as _asyncio

        response = await _asyncio.to_thread(
            llm_client.models.generate_content,
            model=_LLM_PAGINATION_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=50,
                temperature=0.0,
            ),
        )
        text = (response.candidates[0].content.parts[0].text or "").strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        parsed = _json.loads(text)
    except Exception as e:
        logger.warning("LLM pagination fallback failed: %s", e)
        return None

    if not isinstance(parsed, dict) or "index" not in parsed:
        return None

    target_index = parsed["index"]

    # 3. Resolve the element to a backendDOMNodeId via DOM.resolveNode
    resolve_script = (
        """
(() => {
  const els = Array.from(document.querySelectorAll('button, a'))
    .filter(el => (el.textContent || '').trim() || (el.getAttribute('aria-label') || '').trim());
  const el = els[%d];
  if (!el) return null;
  return el;
})()
"""
        % target_index
    )

    # Use Runtime.evaluate with returnByValue=false to get objectId, then DOM.describeNode
    if not hasattr(client, "_send"):
        return None

    try:
        eval_result = await client._send(  # type: ignore[attr-defined]
            "Runtime.evaluate",
            {"expression": resolve_script, "returnByValue": False},
        )
        object_id = eval_result.get("result", {}).get("objectId")
        if not object_id:
            return None
        desc = await client._send(  # type: ignore[attr-defined]
            "DOM.describeNode", {"objectId": object_id}
        )
        return desc.get("node", {}).get("backendNodeId")
    except Exception as e:
        logger.warning("LLM pagination: failed to resolve DOM node: %s", e)
        return None


async def _click_next_page(client: BrowserClient, api_key: str = "") -> Dict[str, Any]:
    """Click pagination Next button using AX tree (Tier 1) or LLM fallback (Tier 2)."""
    # Tier 1: Accessibility tree
    node_id = await _find_next_button_ax(client)
    if node_id is not None and hasattr(client, "click_node_by_backend_id"):
        await client.click_node_by_backend_id(node_id)
        return {"clicked": True, "reason": "ax-tree"}

    # Tier 2: LLM analysis
    if api_key:
        node_id = await _find_next_button_llm(client, api_key)
        if node_id is not None and hasattr(client, "click_node_by_backend_id"):
            await client.click_node_by_backend_id(node_id)
            return {"clicked": True, "reason": "llm-fallback"}

    return {"clicked": False, "reason": "no-next-found"}


async def _wait_for_page_change_after_next(
    client: BrowserClient, prev_card_urls: List[str], timeout: float = _PAGE_CHANGE_TIMEOUT
) -> bool:
    """After clicking Next, poll until card URLs on the page differ from prev_card_urls."""
    quick_collect = """
(() => {
  const selectors = [
    'li.jobs-search-results__list-item',
    'li.scaffold-layout__list-item',
    'li[data-occludable-job-id]',
    'div.job-search-card',
  ];
  const urls = [];
  const seen = new Set();
  for (const sel of selectors) {
    for (const card of document.querySelectorAll(sel)) {
      if (seen.has(card)) continue;
      seen.add(card);
      const a = card.querySelector('a[href*="/jobs/view/"]');
      if (a && a.href) urls.push(String(a.href).split('?')[0]);
    }
  }
  return urls;
})()
"""
    prev_set = set(prev_card_urls)
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(_PAGE_CHANGE_POLL)
        current = await client.evaluate(quick_collect)
        if isinstance(current, list) and current:
            current_set = set(str(u) for u in current)
            if current_set != prev_set:
                return True
    return False


def _format_jobs_with_jd(jobs: List[dict], jd_map: Dict[str, str]) -> str:
    """Format job dicts with optional JD snippets."""
    if not jobs:
        return "No jobs found."
    lines: List[str] = [f"Found {len(jobs)} jobs:"]
    for i, job in enumerate(jobs, start=1):
        title = job.get("title", "")
        company = job.get("company", "")
        location = job.get("location", "")
        url = job.get("url", "")
        lines.append(f"{i}. {title} — {company} ({location})")
        lines.append(f"   Link: {url or 'N/A'}")
        key = _job_dedupe_key(job)
        snippet = jd_map.get(key, "")
        if snippet:
            lines.append(f"   JD: {snippet}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool classes
# ---------------------------------------------------------------------------


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
            "description": "If true, click each card and extract JD from the right pane.",
        },
    }

    def __init__(
        self,
        cdp_port: int = _DEFAULT_CDP_PORT,
        chrome_profile: str = _DEFAULT_CHROME_PROFILE,
        auto_launch: bool = True,
        api_key: str = "",
    ):
        self.cdp_port = cdp_port
        self.chrome_profile = chrome_profile
        self.auto_launch = auto_launch
        self.api_key = api_key

    async def execute(
        self,
        keywords: str = "",
        location: str = "",
        limit: int = 25,
        include_jd: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        if not keywords or not keywords.strip():
            return ToolResult(success=False, output="", error="Missing required parameter: keywords")
        try:
            normalized_limit = _normalize_limit(limit)
        except ValueError as e:
            return ToolResult(success=False, output="", error=str(e))

        client = _build_browser_client(
            cdp_port=self.cdp_port,
            chrome_profile=self.chrome_profile,
            auto_launch=self.auto_launch,
        )

        try:
            await client.connect()

            if await _preflight_login_check(client):
                return ToolResult(success=False, output="", error=_LOGIN_ERROR)

            all_jobs: List[dict] = []
            seen_keys: set[str] = set()
            jd_map: Dict[str, str] = {}
            pages_budget = max(1, (normalized_limit + _PAGE_SIZE - 1) // _PAGE_SIZE)
            include_jd_effective = bool(include_jd)

            start_url = build_search_url(keywords.strip(), location.strip(), start=0)
            await client.navigate(start_url)

            for page in range(pages_budget):
                container = await _find_scroll_container(client)
                if not container:
                    logger.warning("No scroll container found on page %d", page)
                    break

                cards = await _scroll_and_collect_cards(client, container)
                if not cards:
                    break

                if include_jd_effective:
                    for i, card in enumerate(cards):
                        if len(all_jobs) >= normalized_limit:
                            break
                        key = _job_dedupe_key(card)
                        if key in seen_keys:
                            continue
                        detail = await _click_card_and_extract(client, i, include_jd=True)
                        if not detail:
                            # Fall back to card metadata
                            seen_keys.add(key)
                            all_jobs.append(card)
                            continue
                        detail_key = _job_dedupe_key(detail)
                        if detail_key in seen_keys:
                            continue
                        seen_keys.add(detail_key)
                        jd_snippet = _normalize_jd_snippet(detail.pop("jd", ""))
                        all_jobs.append(detail)
                        if jd_snippet:
                            jd_map[detail_key] = jd_snippet
                        await asyncio.sleep(random.uniform(*_CARD_CLICK_JITTER))
                else:
                    for card in cards:
                        if len(all_jobs) >= normalized_limit:
                            break
                        key = _job_dedupe_key(card)
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        all_jobs.append(card)

                if len(all_jobs) >= normalized_limit:
                    break

                # Paginate
                prev_urls = [c.get("url", "") for c in cards if c.get("url")]
                click_result = await _click_next_page(client, api_key=self.api_key)
                if not click_result.get("clicked"):
                    break
                await _human_pagination_delay()
                await _wait_for_page_change_after_next(client, prev_urls)

            all_jobs = all_jobs[:normalized_limit]

            # Build JobListing objects for domain formatter
            job_listings = [
                JobListing(
                    title=j.get("title", ""),
                    company=j.get("company", ""),
                    location=j.get("location", ""),
                    job_id=j.get("jobId", "") or j.get("job_id", ""),
                    url=j.get("url", ""),
                    posted_time=j.get("postedTime", "") or j.get("posted_time", ""),
                )
                for j in all_jobs
            ]

            if jd_map:
                output = _format_jobs_with_jd(all_jobs, jd_map)
            else:
                output = format_job_listings(job_listings)

            return ToolResult(
                success=True,
                output=output,
                data={
                    "jobs": [
                        {
                            "title": j.get("title", ""),
                            "company": j.get("company", ""),
                            "location": j.get("location", ""),
                            "job_id": j.get("jobId", "") or j.get("job_id", ""),
                            "url": j.get("url", ""),
                            "posted_time": j.get("postedTime", "") or j.get("posted_time", ""),
                            "jd": jd_map.get(_job_dedupe_key(j), ""),
                        }
                        for j in all_jobs
                    ],
                    "total": len(all_jobs),
                    "include_jd": include_jd_effective,
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
