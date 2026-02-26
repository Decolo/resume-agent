"""Tests for resume validator tool."""

import json

import pytest

from resume_agent.tools import ResumeValidatorTool


@pytest.fixture
def validator(tmp_path):
    return ResumeValidatorTool(workspace_dir=str(tmp_path))


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


GOOD_RESUME = """\
# Jane Smith
jane@example.com | (555) 123-4567

## Summary
Experienced software engineer with 8+ years building scalable web applications
and distributed systems. Passionate about clean code and mentoring junior developers.

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


class TestValidatorBasics:
    """Core validation tests."""

    @pytest.mark.asyncio
    async def test_good_resume_passes(self, validator, tmp_path):
        path = _write(tmp_path, "resume.md", GOOD_RESUME)
        result = await validator.execute(path=str(path))
        assert result.success
        assert result.data["valid"] is True
        assert len(result.data["errors"]) == 0

    @pytest.mark.asyncio
    async def test_file_not_found(self, validator):
        result = await validator.execute(path="nonexistent.md")
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_empty_file(self, validator, tmp_path):
        path = _write(tmp_path, "empty.md", "")
        result = await validator.execute(path=str(path))
        assert result.success
        assert result.data["valid"] is False
        errors = result.data["errors"]
        assert any(e["check"] == "empty" for e in errors)

    @pytest.mark.asyncio
    async def test_output_contains_status(self, validator, tmp_path):
        path = _write(tmp_path, "resume.md", GOOD_RESUME)
        result = await validator.execute(path=str(path))
        assert "PASS" in result.output

    @pytest.mark.asyncio
    async def test_data_has_format(self, validator, tmp_path):
        path = _write(tmp_path, "resume.md", GOOD_RESUME)
        result = await validator.execute(path=str(path))
        assert result.data["format"] == ".md"


class TestHTMLValidation:
    """Tests for HTML-specific checks."""

    @pytest.mark.asyncio
    async def test_valid_html_passes(self, validator, tmp_path):
        html = (
            '<!DOCTYPE html><html><head><meta charset="UTF-8">'
            "<style>body{}</style></head><body>" + GOOD_RESUME.replace("\n", "<br>") + "</body></html>"
        )
        path = _write(tmp_path, "resume.html", html)
        result = await validator.execute(path=str(path))
        assert result.data["valid"] is True
        assert result.data["format"] == ".html"

    @pytest.mark.asyncio
    async def test_missing_html_tag(self, validator, tmp_path):
        path = _write(tmp_path, "bad.html", "<body>" + GOOD_RESUME + "</body>")
        result = await validator.execute(path=str(path))
        assert any(e["check"] == "html_structure" for e in result.data["errors"])

    @pytest.mark.asyncio
    async def test_missing_charset_warning(self, validator, tmp_path):
        html = "<html><head><style>body{}</style></head><body>" + GOOD_RESUME + "</body></html>"
        path = _write(tmp_path, "nocharset.html", html)
        result = await validator.execute(path=str(path))
        assert any(w["check"] == "html_charset" for w in result.data["warnings"])

    @pytest.mark.asyncio
    async def test_missing_styles_warning(self, validator, tmp_path):
        html = '<html><head><meta charset="UTF-8"></head><body>' + GOOD_RESUME + "</body></html>"
        path = _write(tmp_path, "nostyle.html", html)
        result = await validator.execute(path=str(path))
        assert any(w["check"] == "html_styles" for w in result.data["warnings"])


class TestJSONValidation:
    """Tests for JSON-specific checks."""

    @pytest.mark.asyncio
    async def test_valid_json_resume(self, validator, tmp_path):
        data = {
            "basics": {"name": "Jane Smith", "email": "jane@example.com"},
            "work": [{"company": "Acme", "position": "Engineer"}],
            "education": [{"institution": "State U", "area": "CS"}],
            "skills": [{"name": "Python"}, {"name": "Docker"}],
        }
        # Pad with enough text to pass length check
        data["summary"] = " ".join(["experienced"] * 200)
        path = _write(tmp_path, "resume.json", json.dumps(data, indent=2))
        result = await validator.execute(path=str(path))
        assert result.data["valid"] is True
        assert result.data["format"] == ".json"

    @pytest.mark.asyncio
    async def test_invalid_json(self, validator, tmp_path):
        path = _write(tmp_path, "bad.json", "{invalid json content " + " ".join(["x"] * 200))
        result = await validator.execute(path=str(path))
        assert any(e["check"] == "json_parse" for e in result.data["errors"])

    @pytest.mark.asyncio
    async def test_json_array_root(self, validator, tmp_path):
        path = _write(tmp_path, "array.json", json.dumps([{"name": "test"}] * 50))
        result = await validator.execute(path=str(path))
        assert any(e["check"] == "json_structure" for e in result.data["errors"])

    @pytest.mark.asyncio
    async def test_json_missing_basics(self, validator, tmp_path):
        data = {"work": [{"company": "Acme"}], "padding": " ".join(["word"] * 200)}
        path = _write(tmp_path, "nobasics.json", json.dumps(data, indent=2))
        result = await validator.execute(path=str(path))
        assert any(w["check"] == "json_schema" for w in result.data["warnings"])


class TestContentChecks:
    """Tests for content quality checks."""

    @pytest.mark.asyncio
    async def test_too_short_is_error(self, validator, tmp_path):
        path = _write(tmp_path, "short.md", "# Name\nJust a few words here.")
        result = await validator.execute(path=str(path))
        assert result.data["valid"] is False
        assert any(e["check"] == "length" for e in result.data["errors"])

    @pytest.mark.asyncio
    async def test_short_is_warning(self, validator, tmp_path):
        # 50-150 words should be a warning, not error
        content = "# Name\n\n" + " ".join(["word"] * 80)
        path = _write(tmp_path, "medium.md", content)
        result = await validator.execute(path=str(path))
        assert result.data["valid"] is True  # warnings don't fail
        assert any(w["check"] == "length" for w in result.data["warnings"])

    @pytest.mark.asyncio
    async def test_long_resume_warning(self, validator, tmp_path):
        content = "# Name\n\n" + " ".join(["word"] * 2000)
        path = _write(tmp_path, "long.md", content)
        result = await validator.execute(path=str(path))
        assert any(w["check"] == "length" for w in result.data["warnings"])

    @pytest.mark.asyncio
    async def test_placeholder_text_is_error(self, validator, tmp_path):
        content = GOOD_RESUME + "\nTODO: add more experience\n"
        path = _write(tmp_path, "placeholder.md", content)
        result = await validator.execute(path=str(path))
        assert result.data["valid"] is False
        assert any(e["check"] == "placeholders" for e in result.data["errors"])

    @pytest.mark.asyncio
    async def test_encoding_artifacts_error(self, validator, tmp_path):
        content = GOOD_RESUME.replace("Jane", "Jan\ufffde")
        path = _write(tmp_path, "encoding.md", content)
        result = await validator.execute(path=str(path))
        assert result.data["valid"] is False
        assert any(e["check"] == "encoding" for e in result.data["errors"])
