"""End-to-end integration tests for the resume agent pipeline.

Tests the full flow: parse → ATS score → job match → write → validate → preview.
All tools here are heuristic-based (no LLM calls), so no mocking needed.
"""

import pytest

from packages.core.resume_agent_core.preview import PendingWriteManager
from packages.core.resume_agent_core.templates import AVAILABLE_TEMPLATES
from packages.core.resume_agent_core.tools.ats_scorer import ATSScorerTool
from packages.core.resume_agent_core.tools.job_matcher import JobMatcherTool
from packages.core.resume_agent_core.tools.resume_parser import ResumeParserTool
from packages.core.resume_agent_core.tools.resume_validator import ResumeValidatorTool
from packages.core.resume_agent_core.tools.resume_writer import ResumeWriterTool

SAMPLE_RESUME = """\
# Jane Smith
jane.smith@email.com | (555) 123-4567 | linkedin.com/in/janesmith

## Summary
Experienced software engineer with 8+ years building scalable web applications
and distributed systems. Passionate about clean code and mentoring.

## Experience

### Senior Software Engineer — Acme Corp
Jan 2020 - Present
- Led a team of 5 engineers to deliver a microservices platform
- Developed automated testing framework using Python and pytest
- Implemented CI/CD pipeline with Docker and Kubernetes on AWS
- Reduced deployment time by 60% through automation

### Software Engineer — StartupCo
Jun 2016 - Dec 2019
- Built RESTful APIs with Django and FastAPI
- Optimized PostgreSQL database queries reducing latency by 40%
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

MATCHING_JOB = """\
Senior Software Engineer — Platform Team

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


class TestFullPipeline:
    """End-to-end: parse → ATS score → job match → improve → write → validate."""

    @pytest.mark.asyncio
    async def test_complete_pipeline(self, tmp_path):
        resume_path = tmp_path / "resume.md"
        resume_path.write_text(SAMPLE_RESUME, encoding="utf-8")

        parser = ResumeParserTool(workspace_dir=str(tmp_path))
        scorer = ATSScorerTool(workspace_dir=str(tmp_path))
        matcher = JobMatcherTool(workspace_dir=str(tmp_path))
        writer = ResumeWriterTool(workspace_dir=str(tmp_path))
        validator = ResumeValidatorTool(workspace_dir=str(tmp_path))

        # 1. Parse
        parse_result = await parser.execute(path=str(resume_path))
        assert parse_result.success
        parsed_content = parse_result.output

        # 2. ATS Score
        ats_result = await scorer.execute(path=str(resume_path))
        assert ats_result.success
        initial_score = ats_result.data["overall_score"]
        assert 0 <= initial_score <= 100

        # 3. Job Match
        match_result = await matcher.execute(resume_path=str(resume_path), job_text=MATCHING_JOB)
        assert match_result.success
        match_score = match_result.data["match_score"]
        matched = match_result.data["matched_keywords"]
        missing = match_result.data["missing_keywords"]
        suggestions = match_result.data["suggestions"]

        # Verify match data is coherent
        assert match_score >= 0
        assert isinstance(matched, list)
        assert isinstance(missing, list)
        assert isinstance(suggestions, list)

        # 4. Write improved resume (simulate: add missing keywords to skills)
        improved = parsed_content
        if missing:
            extra_skills = ", ".join(missing[:3])
            improved += f"\n- Additional: {extra_skills}\n"

        output_md = tmp_path / "improved.md"
        write_result = await writer.execute(path=str(output_md), content=improved)
        assert write_result.success

        # 5. Write HTML version
        output_html = tmp_path / "improved.html"
        html_result = await writer.execute(path=str(output_html), content=improved, template="modern")
        assert html_result.success

        # 6. Validate both outputs
        md_valid = await validator.execute(path=str(output_md))
        assert md_valid.success
        assert md_valid.data["valid"] is True

        html_valid = await validator.execute(path=str(output_html))
        assert html_valid.success
        assert html_valid.data["valid"] is True

        # 7. Re-score improved resume
        rescore = await scorer.execute(path=str(output_md))
        assert rescore.success
        # Score should still be reasonable
        assert rescore.data["overall_score"] >= 40

    @pytest.mark.asyncio
    async def test_pipeline_with_json_output(self, tmp_path):
        """Pipeline ending with JSON Resume format."""
        resume_path = tmp_path / "resume.md"
        resume_path.write_text(SAMPLE_RESUME, encoding="utf-8")

        parser = ResumeParserTool(workspace_dir=str(tmp_path))
        writer = ResumeWriterTool(workspace_dir=str(tmp_path))
        validator = ResumeValidatorTool(workspace_dir=str(tmp_path))

        parse_result = await parser.execute(path=str(resume_path))
        assert parse_result.success

        # Write as JSON
        json_path = tmp_path / "resume.json"
        json_result = await writer.execute(path=str(json_path), content=SAMPLE_RESUME)
        assert json_result.success

        # Validate JSON
        valid = await validator.execute(path=str(json_path))
        assert valid.success
        assert valid.data["format"] == ".json"


class TestToolChaining:
    """Test that tool outputs can feed into subsequent tools."""

    @pytest.mark.asyncio
    async def test_parse_then_ats_score(self, tmp_path):
        """Parse a resume, then score it for ATS compatibility."""
        resume_path = tmp_path / "resume.md"
        resume_path.write_text(SAMPLE_RESUME, encoding="utf-8")

        parser = ResumeParserTool(workspace_dir=str(tmp_path))
        scorer = ATSScorerTool(workspace_dir=str(tmp_path))

        # Step 1: Parse
        parse_result = await parser.execute(path=str(resume_path))
        assert parse_result.success
        assert "Jane Smith" in parse_result.output

        # Step 2: ATS Score
        score_result = await scorer.execute(path=str(resume_path))
        assert score_result.success
        assert score_result.data["overall_score"] >= 50

    @pytest.mark.asyncio
    async def test_parse_then_job_match(self, tmp_path):
        """Parse a resume, then match it against a job description."""
        resume_path = tmp_path / "resume.md"
        resume_path.write_text(SAMPLE_RESUME, encoding="utf-8")

        parser = ResumeParserTool(workspace_dir=str(tmp_path))
        matcher = JobMatcherTool(workspace_dir=str(tmp_path))

        parse_result = await parser.execute(path=str(resume_path))
        assert parse_result.success

        match_result = await matcher.execute(resume_path=str(resume_path), job_text=MATCHING_JOB)
        assert match_result.success
        assert match_result.data["match_score"] >= 50
        assert len(match_result.data["matched_keywords"]) > 0

    @pytest.mark.asyncio
    async def test_write_then_validate(self, tmp_path):
        """Write a resume in multiple formats, then validate each."""
        writer = ResumeWriterTool(workspace_dir=str(tmp_path))
        validator = ResumeValidatorTool(workspace_dir=str(tmp_path))

        # Write Markdown
        md_path = tmp_path / "output.md"
        md_result = await writer.execute(path=str(md_path), content=SAMPLE_RESUME)
        assert md_result.success

        md_valid = await validator.execute(path=str(md_path))
        assert md_valid.success
        assert md_valid.data["valid"] is True

        # Write HTML
        html_path = tmp_path / "output.html"
        html_result = await writer.execute(path=str(html_path), content=SAMPLE_RESUME, template="modern")
        assert html_result.success

        html_valid = await validator.execute(path=str(html_path))
        assert html_valid.success
        assert html_valid.data["valid"] is True
        assert html_valid.data["format"] == ".html"

    @pytest.mark.asyncio
    async def test_write_all_templates_then_validate(self, tmp_path):
        """Write HTML with each template and validate all pass."""
        writer = ResumeWriterTool(workspace_dir=str(tmp_path))
        validator = ResumeValidatorTool(workspace_dir=str(tmp_path))

        for template in AVAILABLE_TEMPLATES:
            path = tmp_path / f"resume_{template}.html"
            result = await writer.execute(path=str(path), content=SAMPLE_RESUME, template=template)
            assert result.success, f"Write failed for template: {template}"

            valid = await validator.execute(path=str(path))
            assert valid.success
            assert valid.data["valid"] is True, f"Validation failed for {template}: {valid.data['errors']}"


class TestPreviewPipeline:
    """Test the preview/approve flow with real tools."""

    @pytest.mark.asyncio
    async def test_preview_write_approve_validate(self, tmp_path):
        """Full preview flow: write in preview → approve → validate."""
        writer = ResumeWriterTool(workspace_dir=str(tmp_path))
        validator = ResumeValidatorTool(workspace_dir=str(tmp_path))
        preview_mgr = PendingWriteManager()

        # Enable preview mode
        writer._preview_manager = preview_mgr

        md_path = tmp_path / "resume.md"
        result = await writer.execute(path=str(md_path), content=SAMPLE_RESUME)
        assert result.success
        assert "Successfully wrote" in result.output

        # File should NOT exist yet
        assert not md_path.exists()
        assert preview_mgr.has_pending

        # Approve
        approve_result = preview_mgr.approve(str(md_path))
        assert approve_result.success
        assert md_path.exists()

        # Validate the approved file
        valid = await validator.execute(path=str(md_path))
        assert valid.success
        assert valid.data["valid"] is True

    @pytest.mark.asyncio
    async def test_preview_reject_no_file(self, tmp_path):
        """Rejected preview should not create a file."""
        writer = ResumeWriterTool(workspace_dir=str(tmp_path))
        preview_mgr = PendingWriteManager()
        writer._preview_manager = preview_mgr

        md_path = tmp_path / "rejected.md"
        await writer.execute(path=str(md_path), content=SAMPLE_RESUME)

        preview_mgr.reject(str(md_path))
        assert not md_path.exists()
        assert not preview_mgr.has_pending
