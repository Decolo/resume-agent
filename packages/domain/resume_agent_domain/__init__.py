"""Resume Agent Domain - Pure domain logic for resume operations.

This package contains pure functions with no file system or LLM dependencies.
All I/O is handled by the tools layer; this package operates on strings and dicts.
"""

from .ats_scorer import ATS_KEYWORDS, SCORING_WEIGHTS, ATSScoreResult, format_ats_report, score_ats
from .job_matcher import JobMatchResult, extract_keywords, extract_requirements, format_match_report, match_job
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
    # ATS Scorer
    "score_ats",
    "ATS_KEYWORDS",
    "SCORING_WEIGHTS",
    "ATSScoreResult",
    "format_ats_report",
    # Job Matcher
    "match_job",
    "extract_keywords",
    "extract_requirements",
    "JobMatchResult",
    "format_match_report",
    # Validator
    "validate_resume",
    "ValidationResult",
    "format_validation_report",
]
