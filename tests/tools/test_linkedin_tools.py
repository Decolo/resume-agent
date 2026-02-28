"""Tests for LinkedIn job tools (CDP mocked at system boundary)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from resume_agent.tools.cdp_client import CDPClient
from resume_agent.tools.linkedin_tools import JobDetailTool, JobSearchTool

# Reuse the same fixtures from domain tests
SEARCH_INNER_TEXT = """\
Jobs

Senior Software Engineer
Google
Mountain View, CA
2 days ago

Full Stack Developer
Meta
Menlo Park, CA
1 week ago
"""

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


class TestJobSearchTool:
    @pytest.mark.asyncio
    async def test_search_success(self):
        tool = JobSearchTool(cdp_port=9222)

        mock_client = AsyncMock()
        mock_client.extract_main_text.return_value = SEARCH_INNER_TEXT

        with (
            patch("resume_agent.tools.linkedin_tools.CDPClient", return_value=mock_client),
            patch(_PREFLIGHT_PATCH, return_value=False),
        ):
            result = await tool.execute(keywords="Software Engineer", location="Mountain View")

        assert result.success
        assert result.data["total"] >= 2
        jobs = result.data["jobs"]
        assert any(j["title"] == "Senior Software Engineer" for j in jobs)
        assert any(j["company"] == "Google" for j in jobs)

    @pytest.mark.asyncio
    async def test_pagination_fetches_multiple_pages(self):
        """When limit > 25, tool should navigate multiple pages and merge results."""
        tool = JobSearchTool(cdp_port=9222)

        page1_text = """\
Jobs

Engineer A
Company A
Location A
1 day ago

Engineer B
Company B
Location B
2 days ago
"""
        page2_text = """\
Jobs

Engineer C
Company C
Location C
3 days ago
"""

        mock_client = AsyncMock()
        mock_client.extract_main_text.side_effect = [page1_text, page2_text]

        with (
            patch("resume_agent.tools.linkedin_tools.CDPClient", return_value=mock_client),
            patch(_PREFLIGHT_PATCH, return_value=False),
        ):
            result = await tool.execute(keywords="Engineer", limit=40)

        assert result.success
        assert result.data["total"] == 3
        titles = [j["title"] for j in result.data["jobs"]]
        assert "Engineer A" in titles
        assert "Engineer C" in titles
        # Should have navigated twice (page 1 + page 2)
        assert mock_client.navigate.call_count == 2

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
        # Should NOT have navigated to the search URL
        mock_client.navigate.assert_not_called()


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
            result = await tool.execute(job_id="1234567890")

        assert result.success
        assert result.data["title"] == "Senior Software Engineer"
        assert result.data["company"] == "Google"
        assert "distributed systems" in result.data["description"]

    @pytest.mark.asyncio
    async def test_missing_job_id_returns_error(self):
        tool = JobDetailTool()
        result = await tool.execute(job_id="")

        assert not result.success
        assert "job_id" in result.error.lower()

    @pytest.mark.asyncio
    async def test_chrome_not_running(self):
        tool = JobDetailTool(cdp_port=9222)

        mock_client = AsyncMock()
        mock_client.connect.side_effect = ConnectionError("Connection refused")

        with patch("resume_agent.tools.linkedin_tools.CDPClient", return_value=mock_client):
            result = await tool.execute(job_id="1234567890")

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
            result = await tool.execute(job_id="1234567890")

        assert not result.success
        assert "login" in result.error.lower() or "log in" in result.error.lower()
        # Should NOT have navigated to the detail URL
        mock_client.navigate.assert_not_called()


class TestCDPClientAutoLaunch:
    @pytest.mark.asyncio
    async def test_auto_launches_chrome_on_connection_failure(self):
        client = CDPClient(port=9222, chrome_profile="/tmp/test-profile", auto_launch=True)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"type": "page", "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/ABC"}
        ]
        mock_response.raise_for_status = MagicMock()

        call_count = 0

        async def mock_get(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Connection refused")
            return mock_response

        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = mock_get
        mock_ws = AsyncMock()

        with (
            patch("resume_agent.tools.cdp_client.httpx.AsyncClient", return_value=mock_http),
            patch("resume_agent.tools.cdp_client.websockets.connect", AsyncMock(return_value=mock_ws)),
            patch("resume_agent.tools.cdp_client.subprocess.Popen") as mock_popen,
        ):
            await client.connect()

        mock_popen.assert_called_once()
        launch_args = mock_popen.call_args[0][0]
        assert "--remote-debugging-port=9222" in launch_args
        assert "--user-data-dir=/tmp/test-profile" in launch_args

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
