"""Tests for ATS scoring tool."""

import pytest

from resume_agent.tools import ATSScorerTool


@pytest.fixture
def scorer(tmp_path):
    return ATSScorerTool(workspace_dir=str(tmp_path))


@pytest.fixture
def good_resume(tmp_path):
    """A well-structured resume that should score high."""
    content = """# Jane Smith
jane.smith@email.com | (555) 123-4567 | linkedin.com/in/janesmith

## Summary
Experienced software engineer with 8+ years building scalable web applications.

## Experience

### Senior Software Engineer — Acme Corp
Jan 2020 - Present

- Led a team of 5 engineers to deliver a microservices platform, reducing deployment time by 40%
- Developed automated testing framework that increased code coverage from 60% to 95%
- Implemented CI/CD pipeline serving 200+ deployments per month

### Software Engineer — StartupCo
Jun 2016 - Dec 2019

- Built RESTful APIs handling 10,000+ requests per second
- Optimized database queries, reducing average response time by 35%
- Collaborated with product team to launch 3 major features

## Education

### B.S. Computer Science — State University
2012 - 2016

## Skills

- Languages: Python, JavaScript, TypeScript, Go
- Frameworks: React, Django, FastAPI
- Cloud: AWS, Docker, Kubernetes
- Databases: PostgreSQL, Redis, MongoDB
"""
    path = tmp_path / "good_resume.md"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def weak_resume(tmp_path):
    """A poorly structured resume that should score low."""
    content = """John Doe

I am a hard worker who is looking for a job.

I worked at some company for a while.
I did stuff with computers.
I went to school.
"""
    path = tmp_path / "weak_resume.md"
    path.write_text(content, encoding="utf-8")
    return path


class TestATSScorer:
    """Core scoring tests."""

    @pytest.mark.asyncio
    async def test_good_resume_scores_high(self, scorer, good_resume):
        result = await scorer.execute(path=str(good_resume))
        assert result.success
        assert result.data["overall_score"] >= 70

    @pytest.mark.asyncio
    async def test_weak_resume_scores_low(self, scorer, weak_resume):
        result = await scorer.execute(path=str(weak_resume))
        assert result.success
        assert result.data["overall_score"] < 60

    @pytest.mark.asyncio
    async def test_file_not_found(self, scorer):
        result = await scorer.execute(path="nonexistent.md")
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_empty_file(self, scorer, tmp_path):
        empty = tmp_path / "empty.md"
        empty.write_text("", encoding="utf-8")
        result = await scorer.execute(path=str(empty))
        assert not result.success
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_output_contains_score_breakdown(self, scorer, good_resume):
        result = await scorer.execute(path=str(good_resume))
        assert "Formatting" in result.output
        assert "Completeness" in result.output
        assert "Keywords" in result.output
        assert "Structure" in result.output

    @pytest.mark.asyncio
    async def test_data_has_sections(self, scorer, good_resume):
        result = await scorer.execute(path=str(good_resume))
        sections = result.data["sections"]
        assert "formatting" in sections
        assert "completeness" in sections
        assert "keywords" in sections
        assert "structure" in sections
        for section in sections.values():
            assert "score" in section
            assert "issues" in section
            assert 0 <= section["score"] <= 100


class TestJobDescriptionMatching:
    """Tests for keyword matching against a job description."""

    @pytest.mark.asyncio
    async def test_matching_jd_boosts_score(self, scorer, good_resume):
        jd = "Looking for a Senior Software Engineer with Python, AWS, and Kubernetes experience."
        result = await scorer.execute(path=str(good_resume), job_description=jd)
        assert result.success
        # The good resume has Python, AWS, Kubernetes — should match well
        kw_score = result.data["sections"]["keywords"]["score"]
        assert kw_score >= 60

    @pytest.mark.asyncio
    async def test_mismatched_jd_lowers_score(self, scorer, good_resume):
        jd = "Seeking a Certified Public Accountant with expertise in GAAP, auditing, tax compliance, and QuickBooks."
        result = await scorer.execute(path=str(good_resume), job_description=jd)
        kw_score = result.data["sections"]["keywords"]["score"]
        # Software resume vs accounting job — keyword match should be low
        assert kw_score < 70

    @pytest.mark.asyncio
    async def test_no_jd_still_scores(self, scorer, good_resume):
        result = await scorer.execute(path=str(good_resume))
        assert result.success
        assert result.data["overall_score"] > 0


class TestFormattingChecks:
    """Tests for specific formatting checks."""

    @pytest.mark.asyncio
    async def test_tables_penalized(self, scorer, tmp_path):
        content = "# Resume\n\n| Skill | Level |\n|-------|-------|\n| Python | Expert |\n\n## Experience\nDid things.\n## Education\nWent to school.\n## Skills\n- Python"
        path = tmp_path / "table_resume.md"
        path.write_text(content, encoding="utf-8")
        result = await scorer.execute(path=str(path))
        fmt_issues = result.data["sections"]["formatting"]["issues"]
        assert any("table" in i.lower() for i in fmt_issues)

    @pytest.mark.asyncio
    async def test_special_chars_penalized(self, scorer, tmp_path):
        content = "# Resume\njane@email.com | 555-123-4567\n\n## Experience\n★ Led team\n• Built systems\n✓ Delivered results\n\n## Education\nBS CS 2020\n\n## Skills\n- Python"
        path = tmp_path / "special.md"
        path.write_text(content, encoding="utf-8")
        result = await scorer.execute(path=str(path))
        fmt_issues = result.data["sections"]["formatting"]["issues"]
        assert any("special character" in i.lower() for i in fmt_issues)


class TestCompletenessChecks:
    """Tests for completeness checks."""

    @pytest.mark.asyncio
    async def test_missing_email_flagged(self, scorer, tmp_path):
        content = "# John Doe\n\n## Experience\nWorked at Acme Jan 2020 - Present\n- Led team\n\n## Education\nBS CS\n\n## Skills\n- Python"
        path = tmp_path / "no_email.md"
        path.write_text(content, encoding="utf-8")
        result = await scorer.execute(path=str(path))
        comp_issues = result.data["sections"]["completeness"]["issues"]
        assert any("email" in i.lower() for i in comp_issues)

    @pytest.mark.asyncio
    async def test_missing_experience_flagged(self, scorer, tmp_path):
        content = "# John Doe\njohn@email.com | 555-123-4567\n\n## Education\nBS CS 2020\n\n## Skills\n- Python"
        path = tmp_path / "no_exp.md"
        path.write_text(content, encoding="utf-8")
        result = await scorer.execute(path=str(path))
        comp_issues = result.data["sections"]["completeness"]["issues"]
        assert any("experience" in i.lower() for i in comp_issues)


class TestStructureChecks:
    """Tests for structure checks."""

    @pytest.mark.asyncio
    async def test_short_resume_flagged(self, scorer, tmp_path):
        content = "# Name\nShort resume.\n\n## Experience\nWorked.\n\n## Education\nSchool.\n\n## Skills\n- Stuff"
        path = tmp_path / "short.md"
        path.write_text(content, encoding="utf-8")
        result = await scorer.execute(path=str(path))
        struct_issues = result.data["sections"]["structure"]["issues"]
        assert any("short" in i.lower() for i in struct_issues)

    @pytest.mark.asyncio
    async def test_mixed_bullets_flagged(self, scorer, tmp_path):
        content = "# Name\njane@email.com | 555-123-4567\n\n## Experience\nAcme Corp Jan 2020 - Present\n- Led team of 5 engineers\n* Built platform\n• Delivered results\n\n## Education\nBS CS 2020\n\n## Skills\n- Python"
        path = tmp_path / "mixed.md"
        path.write_text(content, encoding="utf-8")
        result = await scorer.execute(path=str(path))
        struct_issues = result.data["sections"]["structure"]["issues"]
        assert any("bullet" in i.lower() or "inconsistent" in i.lower() for i in struct_issues)
