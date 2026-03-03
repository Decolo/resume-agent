"""Tests for LinkedIn job tools (CDP mocked at system boundary)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from resume_agent.tools.cdp_client import CDPClient
from resume_agent.tools.linkedin_tools import (
    JobDetailTool,
    JobSearchTool,
    _click_next_page,
    _find_next_button_ax,
)

DETAIL_INNER_TEXT = """\
Senior Software Engineer
Google
Mountain View, CA

About the job
We are looking for a Senior Software Engineer to join our Cloud team.
You will design and build scalable distributed systems.

Seniority level
Mid-Senior level

Employment type
Full-time
"""

_PREFLIGHT_PATCH = "resume_agent.tools.linkedin_tools._preflight_login_check"

# Fake card data returned by _scroll_and_collect_cards via evaluate()
_CARDS_PAGE_1 = {
    "cards": [
        {
            "title": "Senior Software Engineer",
            "company": "Google",
            "location": "Mountain View, CA",
            "jobId": "111",
            "url": "https://www.linkedin.com/jobs/view/111",
            "postedTime": "2 days ago",
        },
        {
            "title": "Full Stack Developer",
            "company": "Meta",
            "location": "Menlo Park, CA",
            "jobId": "222",
            "url": "https://www.linkedin.com/jobs/view/222",
            "postedTime": "1 week ago",
        },
    ],
    "atBottom": True,
    "scrollHeight": 800,
}

_CARDS_PAGE_2 = {
    "cards": [
        {
            "title": "Engineer C",
            "company": "Company C",
            "location": "Location C",
            "jobId": "333",
            "url": "https://www.linkedin.com/jobs/view/333",
            "postedTime": "3 days ago",
        },
    ],
    "atBottom": True,
    "scrollHeight": 400,
}

_RIGHT_PANE_DETAIL = {
    "title": "Senior Software Engineer",
    "company": "Google",
    "location": "Mountain View, CA",
    "postedTime": "2 days ago",
    "url": "https://www.linkedin.com/jobs/view/111",
    "jobId": "111",
    "jd": "We are looking for a Senior Software Engineer to join our Cloud team.",
}


def _make_evaluate_side_effect(
    scroll_container: str | None = ".jobs-search-results-list",
    cards_result=None,
    right_pane_ready: bool = True,
    right_pane_detail=None,
    click_card_result=None,
    page_change_urls=None,
):
    """Build an evaluate side_effect that dispatches based on script content."""
    if cards_result is None:
        cards_result = _CARDS_PAGE_1
    if right_pane_detail is None:
        right_pane_detail = _RIGHT_PANE_DETAIL
    if click_card_result is None:
        click_card_result = {"clicked": True, "jobId": "111"}

    call_count = {"scroll_collect": 0}

    async def evaluate(script):
        s = script.strip()
        # _find_scroll_container
        if "data-ra-scroll" in s and "scrollHeight > el.clientHeight" in s:
            return scroll_container
        # _scroll_and_collect_cards — scroll step
        if "scrollBy" in s:
            return None
        # _scroll_and_collect_cards — collect
        if "atBottom" in s and "cards" in s:
            call_count["scroll_collect"] += 1
            if isinstance(cards_result, list):
                idx = min(call_count["scroll_collect"] - 1, len(cards_result) - 1)
                return cards_result[idx]
            return cards_result
        # _wait_for_right_pane
        if "jobs-search__job-details" in s and "paneSelectors" in s and "result" not in s:
            return right_pane_ready
        # _extract_from_right_pane
        if "job-details-jobs-unified-top-card__job-title" in s and "result" in s:
            return right_pane_detail
        # _click_card_and_extract — click script
        if "scrollIntoView" in s and "cards[" in s:
            return click_card_result
        # _wait_for_page_change_after_next
        if "jobs/view" in s and "urls" in s and "atBottom" not in s:
            return page_change_urls or []
        return None

    return evaluate


class TestJobSearchTool:
    @pytest.mark.asyncio
    async def test_search_fast_path_success(self):
        """include_jd=false: scroll left column, collect card metadata."""
        tool = JobSearchTool(cdp_port=9222)

        mock_client = AsyncMock()
        mock_client.evaluate.side_effect = _make_evaluate_side_effect()

        with (
            patch("resume_agent.tools.linkedin_tools.CDPClient", return_value=mock_client),
            patch(_PREFLIGHT_PATCH, return_value=False),
        ):
            result = await tool.execute(keywords="Software Engineer", location="Mountain View")

        assert result.success
        assert result.data["total"] == 2
        jobs = result.data["jobs"]
        assert any(j["title"] == "Senior Software Engineer" for j in jobs)
        assert any(j["company"] == "Google" for j in jobs)

    @pytest.mark.asyncio
    async def test_search_detail_path_with_jd(self):
        """include_jd=true: click each card, extract JD from right pane."""
        tool = JobSearchTool(cdp_port=9222)

        mock_client = AsyncMock()
        mock_client.evaluate.side_effect = _make_evaluate_side_effect(
            right_pane_detail=_RIGHT_PANE_DETAIL,
        )

        with (
            patch("resume_agent.tools.linkedin_tools.CDPClient", return_value=mock_client),
            patch(_PREFLIGHT_PATCH, return_value=False),
            patch("resume_agent.tools.linkedin_tools.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await tool.execute(keywords="Software Engineer", include_jd=True)

        assert result.success
        assert result.data["total"] >= 1
        assert result.data["include_jd"] is True
        # At least one job should have a JD snippet
        jds = [j["jd"] for j in result.data["jobs"] if j["jd"]]
        assert len(jds) >= 1
        assert "Cloud team" in jds[0]

    @pytest.mark.asyncio
    async def test_pagination_fetches_multiple_pages(self):
        """When limit > 25, tool should paginate and merge results."""
        tool = JobSearchTool(cdp_port=9222)

        page1_cards = {
            "cards": [
                {
                    "title": "Engineer A",
                    "company": "Company A",
                    "location": "Location A",
                    "jobId": "1",
                    "url": "https://www.linkedin.com/jobs/view/1",
                    "postedTime": "1 day ago",
                },
                {
                    "title": "Engineer B",
                    "company": "Company B",
                    "location": "Location B",
                    "jobId": "2",
                    "url": "https://www.linkedin.com/jobs/view/2",
                    "postedTime": "2 days ago",
                },
            ],
            "atBottom": True,
            "scrollHeight": 800,
        }
        page2_cards = _CARDS_PAGE_2

        # Track which page we're on via AX tree calls
        page_state = {"current": 0}

        async def evaluate(script):
            s = script.strip()
            if "data-ra-scroll" in s and "scrollHeight > el.clientHeight" in s:
                return ".jobs-search-results-list"
            if "scrollBy" in s:
                return None
            if "atBottom" in s and "cards" in s:
                return page2_cards if page_state["current"] > 0 else page1_cards
            # page change detection — return new URLs
            if "jobs/view" in s and "urls" in s and "atBottom" not in s:
                return ["https://www.linkedin.com/jobs/view/333"]
            return None

        async def fake_get_ax_tree():
            if page_state["current"] == 0:
                page_state["current"] = 1
                return [
                    {"role": {"value": "button"}, "name": {"value": "Next"}, "backendDOMNodeId": 42, "properties": []},
                ]
            return []

        mock_client = AsyncMock()
        mock_client.evaluate.side_effect = evaluate
        mock_client.get_ax_tree = AsyncMock(side_effect=fake_get_ax_tree)
        mock_client.click_node_by_backend_id = AsyncMock()

        with (
            patch("resume_agent.tools.linkedin_tools.CDPClient", return_value=mock_client),
            patch(_PREFLIGHT_PATCH, return_value=False),
            patch("resume_agent.tools.linkedin_tools.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await tool.execute(keywords="Engineer", limit=40)

        assert result.success
        assert result.data["total"] == 3
        titles = [j["title"] for j in result.data["jobs"]]
        assert "Engineer A" in titles
        assert "Engineer C" in titles

    @pytest.mark.asyncio
    async def test_missing_keywords_returns_error(self):
        tool = JobSearchTool()
        result = await tool.execute(keywords="")

        assert not result.success
        assert "keywords" in result.error.lower()

    @pytest.mark.asyncio
    async def test_chrome_not_running(self):
        tool = JobSearchTool(cdp_port=9222)

        mock_client = AsyncMock()
        mock_client.connect.side_effect = ConnectionError("Connection refused")

        with patch("resume_agent.tools.linkedin_tools.CDPClient", return_value=mock_client):
            result = await tool.execute(keywords="Engineer")

        assert not result.success
        assert "Chrome" in result.error or "connect" in result.error.lower()

    @pytest.mark.asyncio
    async def test_login_required_returns_error(self):
        tool = JobSearchTool(cdp_port=9222)

        mock_client = AsyncMock()

        with (
            patch("resume_agent.tools.linkedin_tools.CDPClient", return_value=mock_client),
            patch(_PREFLIGHT_PATCH, return_value=True),
        ):
            result = await tool.execute(keywords="Engineer")

        assert not result.success
        assert "login" in result.error.lower() or "log in" in result.error.lower()
        mock_client.navigate.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_scroll_container_returns_empty(self):
        """When no scrollable container is found, return empty results."""
        tool = JobSearchTool(cdp_port=9222)

        mock_client = AsyncMock()
        mock_client.evaluate.side_effect = _make_evaluate_side_effect(scroll_container=None)

        with (
            patch("resume_agent.tools.linkedin_tools.CDPClient", return_value=mock_client),
            patch(_PREFLIGHT_PATCH, return_value=False),
        ):
            result = await tool.execute(keywords="Engineer")

        assert result.success
        assert result.data["total"] == 0


class TestJobDetailTool:
    @pytest.mark.asyncio
    async def test_detail_success(self):
        tool = JobDetailTool(cdp_port=9222)

        mock_client = AsyncMock()
        mock_client.extract_main_text.return_value = DETAIL_INNER_TEXT

        with (
            patch("resume_agent.tools.linkedin_tools.CDPClient", return_value=mock_client),
            patch(_PREFLIGHT_PATCH, return_value=False),
        ):
            result = await tool.execute(job_url="https://www.linkedin.com/jobs/view/1234567890/")

        assert result.success
        assert result.data["title"] == "Senior Software Engineer"
        assert result.data["company"] == "Google"
        assert "distributed systems" in result.data["description"]

    @pytest.mark.asyncio
    async def test_missing_job_url_returns_error(self):
        tool = JobDetailTool()
        result = await tool.execute(job_url="")

        assert not result.success
        assert "job_url" in result.error.lower()

    @pytest.mark.asyncio
    async def test_invalid_job_url_returns_error(self):
        tool = JobDetailTool()
        result = await tool.execute(job_url="https://example.com/jobs/view/123")

        assert not result.success
        assert "invalid job_url" in result.error.lower()

    @pytest.mark.asyncio
    async def test_chrome_not_running(self):
        tool = JobDetailTool(cdp_port=9222)

        mock_client = AsyncMock()
        mock_client.connect.side_effect = ConnectionError("Connection refused")

        with patch("resume_agent.tools.linkedin_tools.CDPClient", return_value=mock_client):
            result = await tool.execute(job_url="https://www.linkedin.com/jobs/view/1234567890/")

        assert not result.success
        assert "Chrome" in result.error or "connect" in result.error.lower()

    @pytest.mark.asyncio
    async def test_login_required_returns_error(self):
        tool = JobDetailTool(cdp_port=9222)

        mock_client = AsyncMock()

        with (
            patch("resume_agent.tools.linkedin_tools.CDPClient", return_value=mock_client),
            patch(_PREFLIGHT_PATCH, return_value=True),
        ):
            result = await tool.execute(job_url="https://www.linkedin.com/jobs/view/1234567890/")

        assert not result.success
        assert "login" in result.error.lower() or "log in" in result.error.lower()
        mock_client.navigate.assert_not_called()

    @pytest.mark.asyncio
    async def test_detail_success_not_overridden_by_close_error(self):
        tool = JobDetailTool(cdp_port=9222)

        mock_client = AsyncMock()
        mock_client.extract_main_text.return_value = DETAIL_INNER_TEXT
        mock_client.close.side_effect = RuntimeError("cleanup failed")

        with (
            patch("resume_agent.tools.linkedin_tools.CDPClient", return_value=mock_client),
            patch(_PREFLIGHT_PATCH, return_value=False),
        ):
            result = await tool.execute(job_url="https://www.linkedin.com/jobs/view/1234567890/")

        assert result.success
        assert result.data["title"] == "Senior Software Engineer"


class TestClickNextPageAXTree:
    """Tests for AX-tree based pagination (Tier 1)."""

    @pytest.mark.asyncio
    async def test_ax_tree_finds_next_button(self):
        """Tier 1: AX tree returns a node with role=button, name='Next' → returns backendDOMNodeId."""
        mock_client = AsyncMock()
        mock_client.get_ax_tree = AsyncMock(
            return_value=[
                {"role": {"value": "button"}, "name": {"value": "Previous"}, "backendDOMNodeId": 10, "properties": []},
                {"role": {"value": "button"}, "name": {"value": "Next"}, "backendDOMNodeId": 42, "properties": []},
                {"role": {"value": "link"}, "name": {"value": "About"}, "backendDOMNodeId": 99, "properties": []},
            ]
        )

        result = await _find_next_button_ax(mock_client)
        assert result == 42

    @pytest.mark.asyncio
    async def test_ax_tree_skips_disabled_next_button(self):
        """Tier 1: disabled Next button is skipped, returns None."""
        mock_client = AsyncMock()
        mock_client.get_ax_tree = AsyncMock(
            return_value=[
                {
                    "role": {"value": "button"},
                    "name": {"value": "Next"},
                    "backendDOMNodeId": 42,
                    "properties": [{"name": "disabled", "value": {"value": True}}],
                },
            ]
        )

        result = await _find_next_button_ax(mock_client)
        assert result is None

    @pytest.mark.asyncio
    async def test_ax_tree_no_match_returns_none(self):
        """Tier 1: no pagination button in AX tree → returns None."""
        mock_client = AsyncMock()
        mock_client.get_ax_tree = AsyncMock(
            return_value=[
                {"role": {"value": "button"}, "name": {"value": "Apply"}, "backendDOMNodeId": 10, "properties": []},
                {"role": {"value": "link"}, "name": {"value": "Home"}, "backendDOMNodeId": 20, "properties": []},
            ]
        )

        result = await _find_next_button_ax(mock_client)
        assert result is None

    @pytest.mark.asyncio
    async def test_click_next_page_tier1_ax_tree(self):
        """_click_next_page: AX tree match → clicks via click_node_by_backend_id."""
        mock_client = AsyncMock()
        mock_client.get_ax_tree = AsyncMock(
            return_value=[
                {"role": {"value": "button"}, "name": {"value": "Next"}, "backendDOMNodeId": 42, "properties": []},
            ]
        )
        mock_client.click_node_by_backend_id = AsyncMock()

        result = await _click_next_page(mock_client)
        assert result == {"clicked": True, "reason": "ax-tree"}
        mock_client.click_node_by_backend_id.assert_awaited_once_with(42)

    @pytest.mark.asyncio
    async def test_click_next_page_tier2_llm_fallback(self):
        """_click_next_page: AX tree misses → LLM fallback identifies button."""
        mock_client = AsyncMock()
        mock_client.get_ax_tree = AsyncMock(return_value=[])  # no AX match
        mock_client.click_node_by_backend_id = AsyncMock()

        with patch(
            "resume_agent.tools.linkedin_tools._find_next_button_llm",
            AsyncMock(return_value=99),
        ):
            result = await _click_next_page(mock_client, api_key="fake-key")

        assert result == {"clicked": True, "reason": "llm-fallback"}
        mock_client.click_node_by_backend_id.assert_awaited_once_with(99)

    @pytest.mark.asyncio
    async def test_click_next_page_both_miss(self):
        """_click_next_page: both tiers miss → returns not found."""
        mock_client = AsyncMock()
        mock_client.get_ax_tree = AsyncMock(return_value=[])

        with patch(
            "resume_agent.tools.linkedin_tools._find_next_button_llm",
            AsyncMock(return_value=None),
        ):
            result = await _click_next_page(mock_client, api_key="fake-key")

        assert result == {"clicked": False, "reason": "no-next-found"}


class TestCDPClientAutoLaunch:
    @pytest.mark.asyncio
    async def test_auto_launches_chrome_on_port_zero(self):
        """When port=0 and auto_launch=True, connect() runs _prepare_and_launch_chrome."""
        client = CDPClient(port=0, chrome_profile="/tmp/test-profile", auto_launch=True)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"type": "page", "webSocketDebuggerUrl": "ws://localhost:54321/devtools/page/ABC"}
        ]
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_ws = AsyncMock()

        with (
            patch("resume_agent.tools.cdp_client.httpx.AsyncClient", return_value=mock_http),
            patch("resume_agent.tools.cdp_client.websockets.connect", AsyncMock(return_value=mock_ws)),
            patch("resume_agent.tools.cdp_client._prepare_and_launch_chrome", return_value=54321),
        ):
            await client.connect()

        assert client.port == 54321

    @pytest.mark.asyncio
    async def test_no_auto_launch_when_disabled(self):
        client = CDPClient(port=9222, auto_launch=False)

        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(side_effect=ConnectionError("Connection refused"))

        with (
            patch("resume_agent.tools.cdp_client.httpx.AsyncClient", return_value=mock_http),
            patch("resume_agent.tools.cdp_client.subprocess.Popen") as mock_popen,
        ):
            with pytest.raises(ConnectionError):
                await client.connect()

        mock_popen.assert_not_called()
