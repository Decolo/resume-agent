"""Tests for LinkedIn job search domain logic (pure functions, no I/O)."""

from resume_agent.domain.linkedin_jobs import (
    JobDetail,
    JobListing,
    build_detail_url,
    build_search_url,
    check_login_required,
    format_job_detail,
    format_job_listings,
    parse_job_detail,
    parse_job_listings,
)

# ---------------------------------------------------------------------------
# Fixtures — realistic innerText captured from LinkedIn search pages
# ---------------------------------------------------------------------------

SEARCH_PAGE_TEXT = """\
Jobs

Senior Software Engineer
Google
Mountain View, CA
2 days ago

Full Stack Developer
Meta
Menlo Park, CA
1 week ago

Backend Engineer
Amazon
Seattle, WA
3 days ago
Actively recruiting

Data Scientist
Netflix
Los Gatos, CA
Just now
"""


class TestParseJobListings:
    def test_extracts_jobs_from_search_text(self):
        jobs = parse_job_listings(SEARCH_PAGE_TEXT)

        assert len(jobs) >= 3
        assert all(isinstance(j, JobListing) for j in jobs)

        # Verify first job has expected fields populated
        titles = [j.title for j in jobs]
        companies = [j.company for j in jobs]
        locations = [j.location for j in jobs]

        assert "Senior Software Engineer" in titles
        assert "Google" in companies
        assert "Mountain View, CA" in locations

    def test_empty_text_returns_empty_list(self):
        assert parse_job_listings("") == []
        assert parse_job_listings("   \n\n  ") == []
        assert parse_job_listings("Jobs\nSearch results") == []


DETAIL_PAGE_TEXT = """\
Senior Software Engineer
Google
Mountain View, CA

About the job
We are looking for a Senior Software Engineer to join our Cloud team.
You will design and build scalable distributed systems.

Qualifications:
- 5+ years of experience in software engineering
- Proficiency in Python, Java, or Go
- Experience with distributed systems

Seniority level
Mid-Senior level

Employment type
Full-time

Job function
Engineering and Information Technology

Industries
Technology, Information and Internet

Posted 2 days ago · 150 applicants
"""


class TestParseJobDetail:
    def test_extracts_description_from_detail_text(self):
        detail = parse_job_detail(DETAIL_PAGE_TEXT)

        assert isinstance(detail, JobDetail)
        assert detail.title == "Senior Software Engineer"
        assert detail.company == "Google"
        assert detail.location == "Mountain View, CA"
        assert "scalable distributed systems" in detail.description
        assert "5+ years" in detail.description


class TestFormatJobListings:
    def test_readable_output(self):
        jobs = [
            JobListing(
                title="Engineer",
                company="Acme",
                location="NYC",
                posted_time="1d ago",
                url="https://www.linkedin.com/jobs/view/111/",
            ),
            JobListing(title="Designer", company="Beta", location="LA", url="https://www.linkedin.com/jobs/view/222/"),
        ]
        output = format_job_listings(jobs)

        assert "Engineer" in output
        assert "Acme" in output
        assert "linkedin.com/jobs/view/111" in output
        assert "Designer" in output
        assert "linkedin.com/jobs/view/222" in output
        # Should be compact — no posted_time in listing output
        assert "1d ago" not in output

    def test_empty_list(self):
        output = format_job_listings([])
        assert "no" in output.lower() or output.strip() == ""


class TestFormatJobDetail:
    def test_readable_output(self):
        detail = JobDetail(
            title="Engineer",
            company="Acme",
            location="NYC",
            description="Build cool stuff.\nRequires Python.",
            seniority_level="Mid-Senior",
            employment_type="Full-time",
        )
        output = format_job_detail(detail)

        assert "Engineer" in output
        assert "Acme" in output
        assert "Build cool stuff" in output
        assert "Mid-Senior" in output


class TestUrlBuilders:
    def test_build_search_url(self):
        url = build_search_url("Software Engineer", "San Francisco")
        assert "linkedin.com/jobs/search" in url
        assert "Software" in url or "Software+Engineer" in url
        assert "San" in url or "San+Francisco" in url

    def test_build_search_url_no_location(self):
        url = build_search_url("Python Developer")
        assert "linkedin.com/jobs/search" in url
        assert "location" not in url

    def test_build_search_url_with_start_offset(self):
        url = build_search_url("Engineer", "Seattle", start=25)
        assert "start=25" in url

    def test_build_detail_url(self):
        url = build_detail_url("1234567890")
        assert "linkedin.com/jobs/view/1234567890" in url


class TestCheckLoginRequired:
    def test_detects_sign_in_page(self):
        text = """\
Sign in
Stay updated on your professional world

Email or phone

Password

Sign in

Forgot password?

New to LinkedIn? Join now
"""
        assert check_login_required(text) is True

    def test_detects_join_now_page(self):
        text = "Join LinkedIn\nSign up to stay connected\nFirst name\nLast name\nEmail"
        assert check_login_required(text) is True

    def test_detects_authwall(self):
        text = "Sign in to view more\nJoin now to see full results\nSenior Engineer at Google"
        assert check_login_required(text) is True

    def test_normal_page_not_flagged(self):
        assert check_login_required(SEARCH_PAGE_TEXT) is False
        assert check_login_required(DETAIL_PAGE_TEXT) is False
