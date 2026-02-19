"""Tests for HTML resume templates."""

import pytest

from packages.core.resume_agent_core.templates import AVAILABLE_TEMPLATES, load_template_css


class TestTemplateLoading:
    """Tests for CSS template loading."""

    def test_available_templates_list(self):
        assert "modern" in AVAILABLE_TEMPLATES
        assert "classic" in AVAILABLE_TEMPLATES
        assert "minimal" in AVAILABLE_TEMPLATES
        assert "creative" in AVAILABLE_TEMPLATES
        assert len(AVAILABLE_TEMPLATES) == 4

    @pytest.mark.parametrize("template", AVAILABLE_TEMPLATES)
    def test_load_each_template(self, template):
        css = load_template_css(template)
        assert isinstance(css, str)
        assert len(css) > 100  # non-trivial CSS

    def test_unknown_template_falls_back_to_modern(self):
        css = load_template_css("nonexistent")
        modern_css = load_template_css("modern")
        assert css == modern_css

    def test_templates_are_different(self):
        styles = {t: load_template_css(t) for t in AVAILABLE_TEMPLATES}
        # Each template should be unique
        unique = set(styles.values())
        assert len(unique) == len(AVAILABLE_TEMPLATES)


class TestModernTemplate:
    """Tests for modern.css content."""

    def test_has_resume_container(self):
        css = load_template_css("modern")
        assert ".resume-container" in css

    def test_has_print_media_query(self):
        css = load_template_css("modern")
        assert "@media print" in css

    def test_uses_sans_serif(self):
        css = load_template_css("modern")
        assert "sans-serif" in css

    def test_has_box_shadow(self):
        css = load_template_css("modern")
        assert "box-shadow" in css


class TestClassicTemplate:
    """Tests for classic.css content."""

    def test_uses_serif(self):
        css = load_template_css("classic")
        assert "serif" in css

    def test_has_double_border(self):
        css = load_template_css("classic")
        assert "double" in css

    def test_has_print_media_query(self):
        css = load_template_css("classic")
        assert "@media print" in css


class TestMinimalTemplate:
    """Tests for minimal.css content."""

    def test_uses_helvetica(self):
        css = load_template_css("minimal")
        assert "Helvetica" in css

    def test_has_muted_colors(self):
        css = load_template_css("minimal")
        # Minimal uses muted grays
        assert "#888" in css or "#aaa" in css

    def test_list_style_none(self):
        css = load_template_css("minimal")
        assert "list-style-type: none" in css


class TestCreativeTemplate:
    """Tests for creative.css content."""

    def test_has_gradient(self):
        css = load_template_css("creative")
        assert "gradient" in css

    def test_has_border_radius(self):
        css = load_template_css("creative")
        assert "border-radius" in css

    def test_has_print_media_query(self):
        css = load_template_css("creative")
        assert "@media print" in css
