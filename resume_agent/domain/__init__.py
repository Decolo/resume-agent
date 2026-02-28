"""Resume Agent Domain - Pure domain logic for resume operations.

This package contains pure functions with no file system or LLM dependencies.
All I/O is handled by the tools layer; this package operates on strings and dicts.
"""

from .job_matcher import JobMatchResult, extract_keywords, extract_requirements, format_match_report, match_job
from .linkedin_jobs import (
    JobDetail,
    JobListing,
    build_detail_url,
    build_search_url,
    format_job_detail,
    format_job_listings,
    parse_job_detail,
    parse_job_listings,
)
from .resume_linter import LINT_KEYWORDS, LINT_WEIGHTS, LintResult, format_lint_report, lint_resume
from .resume_parser import extract_sections, json_resume_to_text
from .resume_validator import ValidationResult, format_validation_report, validate_resume
from .resume_writer import markdown_to_html, markdown_to_json_resume, markdown_to_plain_text

__all__ = [
    # Parser
    "extract_sections",
    "json_resume_to_text",
    # Writer
    "markdown_to_plain_text",
    "markdown_to_json_resume",
    "markdown_to_html",
    # Resume Linter
    "lint_resume",
    "LINT_KEYWORDS",
    "LINT_WEIGHTS",
    "LintResult",
    "format_lint_report",
    # Job Matcher
    "match_job",
    "extract_keywords",
    "extract_requirements",
    "JobMatchResult",
    "format_match_report",
    # LinkedIn Jobs
    "JobListing",
    "JobDetail",
    "parse_job_listings",
    "parse_job_detail",
    "format_job_listings",
    "format_job_detail",
    "build_search_url",
    "build_detail_url",
    # Validator
    "validate_resume",
    "ValidationResult",
    "format_validation_report",
]
