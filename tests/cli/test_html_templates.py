"""Tests for HTML resume templates."""

import pytest

from resume_agent.core.templates import AVAILABLE_TEMPLATES, load_template_css


def test_available_templates_exposes_all_supported_template_names() -> None:
    assert AVAILABLE_TEMPLATES == ["modern", "classic", "minimal", "creative"]


@pytest.mark.parametrize("template", AVAILABLE_TEMPLATES)
def test_load_template_css_returns_nontrivial_styles_for_each_supported_template(template: str) -> None:
    css = load_template_css(template)
    assert isinstance(css, str)
    assert len(css) > 100


def test_load_template_css_falls_back_to_modern_when_template_name_is_unknown() -> None:
    assert load_template_css("nonexistent") == load_template_css("modern")


def test_supported_templates_do_not_share_identical_css_payloads() -> None:
    styles = {template: load_template_css(template) for template in AVAILABLE_TEMPLATES}
    assert len(set(styles.values())) == len(AVAILABLE_TEMPLATES)
