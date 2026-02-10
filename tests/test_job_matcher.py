"""Tests for job description matching tool."""

import pytest

from resume_agent.tools.job_matcher import JobMatcherTool


@pytest.fixture
def matcher(tmp_path):
    return JobMatcherTool(workspace_dir=str(tmp_path))


@pytest.fixture
def sample_resume(tmp_path):
    content = """# Jane Smith
jane.smith@email.com | (555) 123-4567 | linkedin.com/in/janesmith

## Summary
Experienced software engineer with 8+ years building scalable web applications.

## Experience

### Senior Software Engineer — Acme Corp
Jan 2020 - Present

- Led a team of 5 engineers to deliver a microservices platform
- Developed automated testing framework using Python and pytest
- Implemented CI/CD pipeline with Docker and Kubernetes on AWS

### Software Engineer — StartupCo
Jun 2016 - Dec 2019

- Built RESTful APIs with Django and FastAPI
- Optimized PostgreSQL database queries
- Collaborated with product team using Agile methodology

## Education

### B.S. Computer Science — State University
2012 - 2016

## Skills

- Languages: Python, JavaScript, TypeScript, Go
- Frameworks: React, Django, FastAPI, Node.js
- Cloud: AWS, Docker, Kubernetes
- Databases: PostgreSQL, Redis, MongoDB
"""
    path = tmp_path / "resume.md"
    path.write_text(content, encoding="utf-8")
    return path


MATCHING_JD = """
Senior Software Engineer

We are looking for a Senior Software Engineer to join our platform team.

Requirements:
- 5+ years of experience in software engineering
- Strong proficiency in Python and JavaScript
- Experience with AWS, Docker, and Kubernetes
- Familiarity with PostgreSQL or similar databases
- Experience building RESTful APIs

Preferred:
- Experience with React or similar frontend frameworks
- Knowledge of CI/CD pipelines
- Experience with microservices architecture
"""

MISMATCHED_JD = """
Senior Data Scientist

We are looking for a Senior Data Scientist to lead our ML team.

Requirements:
- PhD in Statistics, Mathematics, or related field
- 5+ years experience with machine learning and deep learning
- Proficiency in R, SAS, and SPSS
- Experience with TensorFlow and PyTorch
- Strong background in statistical modeling and hypothesis testing

Preferred:
- Experience with Spark and Hadoop
- Published research in peer-reviewed journals
"""


class TestJobMatcher:
    """Core matching tests."""

    @pytest.mark.asyncio
    async def test_good_match_scores_high(self, matcher, sample_resume):
        result = await matcher.execute(
            resume_path=str(sample_resume), job_text=MATCHING_JD
        )
        assert result.success
        assert result.data["match_score"] >= 60

    @pytest.mark.asyncio
    async def test_poor_match_scores_low(self, matcher, sample_resume):
        result = await matcher.execute(
            resume_path=str(sample_resume), job_text=MISMATCHED_JD
        )
        assert result.success
        assert result.data["match_score"] < 70

    @pytest.mark.asyncio
    async def test_file_not_found(self, matcher):
        result = await matcher.execute(
            resume_path="nonexistent.md", job_text="Some job"
        )
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_empty_resume(self, matcher, tmp_path):
        empty = tmp_path / "empty.md"
        empty.write_text("", encoding="utf-8")
        result = await matcher.execute(
            resume_path=str(empty), job_text="Some job"
        )
        assert not result.success
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_no_jd_provided(self, matcher, sample_resume):
        result = await matcher.execute(resume_path=str(sample_resume))
        assert not result.success
        assert "job_text" in result.error.lower() or "job_url" in result.error.lower()

    @pytest.mark.asyncio
    async def test_job_url_without_fetch(self, matcher, sample_resume):
        result = await matcher.execute(
            resume_path=str(sample_resume), job_url="https://example.com/job"
        )
        assert not result.success
        assert "web_read" in result.error.lower()


class TestMatchOutput:
    """Tests for output structure."""

    @pytest.mark.asyncio
    async def test_data_has_required_fields(self, matcher, sample_resume):
        result = await matcher.execute(
            resume_path=str(sample_resume), job_text=MATCHING_JD
        )
        assert "match_score" in result.data
        assert "matched_keywords" in result.data
        assert "missing_keywords" in result.data
        assert "suggestions" in result.data
        assert "requirements" in result.data

    @pytest.mark.asyncio
    async def test_matched_keywords_are_relevant(self, matcher, sample_resume):
        result = await matcher.execute(
            resume_path=str(sample_resume), job_text=MATCHING_JD
        )
        matched = result.data["matched_keywords"]
        # The resume has Python, AWS, Docker, Kubernetes — should match
        assert any("python" in kw for kw in matched)

    @pytest.mark.asyncio
    async def test_missing_keywords_for_mismatched_jd(self, matcher, sample_resume):
        result = await matcher.execute(
            resume_path=str(sample_resume), job_text=MISMATCHED_JD
        )
        missing = result.data["missing_keywords"]
        # Data science JD should have missing keywords like tensorflow, pytorch, etc.
        assert len(missing) > 0

    @pytest.mark.asyncio
    async def test_output_contains_sections(self, matcher, sample_resume):
        result = await matcher.execute(
            resume_path=str(sample_resume), job_text=MATCHING_JD
        )
        assert "Match Score" in result.output
        assert "Matching Keywords" in result.output or "Missing Keywords" in result.output

    @pytest.mark.asyncio
    async def test_suggestions_are_actionable(self, matcher, sample_resume):
        result = await matcher.execute(
            resume_path=str(sample_resume), job_text=MISMATCHED_JD
        )
        suggestions = result.data["suggestions"]
        # Should have suggestions for a mismatched resume
        assert len(suggestions) > 0
        for s in suggestions:
            assert "section" in s
            assert "action" in s
            assert "detail" in s


class TestRequirementsExtraction:
    """Tests for job description parsing."""

    @pytest.mark.asyncio
    async def test_extracts_required_skills(self, matcher, sample_resume):
        result = await matcher.execute(
            resume_path=str(sample_resume), job_text=MATCHING_JD
        )
        reqs = result.data["requirements"]
        assert len(reqs.get("required_skills", [])) > 0

    @pytest.mark.asyncio
    async def test_extracts_preferred_skills(self, matcher, sample_resume):
        result = await matcher.execute(
            resume_path=str(sample_resume), job_text=MATCHING_JD
        )
        reqs = result.data["requirements"]
        assert len(reqs.get("preferred_skills", [])) > 0

    @pytest.mark.asyncio
    async def test_extracts_experience_years(self, matcher, sample_resume):
        result = await matcher.execute(
            resume_path=str(sample_resume), job_text=MATCHING_JD
        )
        reqs = result.data["requirements"]
        quals = reqs.get("qualifications", [])
        assert any("years" in q.lower() for q in quals)
