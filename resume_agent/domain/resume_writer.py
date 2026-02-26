"""Pure domain logic for resume format conversion.

All functions accept and return strings -- no file I/O.
The tools layer is responsible for reading/writing files.
"""

from __future__ import annotations

import json
import re

# ---------------------------------------------------------------------------
# Markdown → Plain text
# ---------------------------------------------------------------------------


def markdown_to_plain_text(content: str) -> str:
    """Strip Markdown formatting and return plain text."""
    text = content
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    return text


# ---------------------------------------------------------------------------
# Markdown → JSON Resume
# ---------------------------------------------------------------------------


def markdown_to_json_resume(content: str) -> str:
    """Convert Markdown resume text to a JSON Resume string."""
    resume: dict = {
        "basics": {
            "name": "",
            "label": "",
            "email": "",
            "phone": "",
            "summary": "",
        },
        "work": [],
        "education": [],
        "skills": [],
    }

    lines = content.split("\n")
    current_section: str | None = None

    for line in lines:
        line = line.strip()

        if not resume["basics"]["name"] and line and line.startswith("#"):
            resume["basics"]["name"] = line.lstrip("#").strip()
            continue

        if re.match(r"^##?\s*(summary|objective|profile|about)", line, re.I):
            current_section = "summary"
        elif re.match(r"^##?\s*(experience|work|employment)", line, re.I):
            current_section = "work"
        elif re.match(r"^##?\s*(education|academic)", line, re.I):
            current_section = "education"
        elif re.match(r"^##?\s*(skills|technical)", line, re.I):
            current_section = "skills"
        elif current_section == "summary" and line:
            resume["basics"]["summary"] += line + " "
        elif current_section == "skills" and line.startswith("-"):
            skill_text = line.lstrip("- ").strip()
            if ":" in skill_text:
                name, keywords = skill_text.split(":", 1)
                resume["skills"].append(
                    {
                        "name": name.strip(),
                        "keywords": [k.strip() for k in keywords.split(",")],
                    }
                )
            else:
                resume["skills"].append({"name": skill_text, "keywords": []})

        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", line)
        if email_match and not resume["basics"]["email"]:
            resume["basics"]["email"] = email_match.group()

        phone_match = re.search(r"[\+]?[\d\-\(\)\s]{10,}", line)
        if phone_match and not resume["basics"]["phone"]:
            resume["basics"]["phone"] = phone_match.group().strip()

    resume["basics"]["summary"] = resume["basics"]["summary"].strip()
    return json.dumps(resume, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Markdown → HTML
# ---------------------------------------------------------------------------

#: Minimal fallback CSS when no template is provided.
_FALLBACK_CSS = """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: sans-serif; line-height: 1.6; color: #333; }
        .resume-container { max-width: 800px; margin: 0 auto; padding: 40px; }
        h1 { font-size: 2em; margin-bottom: 0.2em; }
        h2 { font-size: 1.2em; margin-top: 1.5em; border-bottom: 1px solid #ccc; }
        p { margin-bottom: 0.8em; }
        ul { margin-left: 1.5em; }
        li { margin-bottom: 0.3em; }
        a { color: #0066cc; }
"""


def markdown_to_html(content: str, css: str | None = None) -> str:
    """Convert Markdown resume to a standalone HTML document.

    *css* is injected into a ``<style>`` tag.  Falls back to
    ``_FALLBACK_CSS`` when *css* is ``None``.
    """
    try:
        import markdown as md_lib

        html_body = md_lib.markdown(content, extensions=["tables", "fenced_code"])
    except ImportError:
        html_body = _basic_md_to_html(content)

    styles = css if css is not None else _FALLBACK_CSS

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '    <meta charset="UTF-8">\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        "    <title>Resume</title>\n"
        "    <style>\n"
        f"{styles}\n"
        "    </style>\n"
        "</head>\n"
        "<body>\n"
        '    <div class="resume-container">\n'
        f"{html_body}\n"
        "    </div>\n"
        "</body>\n"
        "</html>"
    )


def _basic_md_to_html(content: str) -> str:
    """Minimal Markdown → HTML without the ``markdown`` library."""
    html = content
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = re.sub(r"(<li>.*</li>\n)+", r"<ul>\g<0></ul>", html)
    html = re.sub(r"\n\n+", r"</p><p>", html)
    html = f"<p>{html}</p>"
    html = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', html)
    return html
