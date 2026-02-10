"""Resume HTML templates — CSS files for different resume styles."""

from pathlib import Path

_TEMPLATE_DIR = Path(__file__).parent

AVAILABLE_TEMPLATES = ["modern", "classic", "minimal", "creative"]


def load_template_css(template: str) -> str:
    """Load CSS for a given template name.

    Args:
        template: One of 'modern', 'classic', 'minimal', 'creative'

    Returns:
        CSS string, or modern template as fallback
    """
    if template not in AVAILABLE_TEMPLATES:
        template = "modern"

    css_path = _TEMPLATE_DIR / f"{template}.css"
    if css_path.exists():
        return css_path.read_text(encoding="utf-8")

    # Fallback to modern
    return (_TEMPLATE_DIR / "modern.css").read_text(encoding="utf-8")
