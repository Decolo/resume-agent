"""Resume writer tool - generate resumes in various formats."""

import json
from pathlib import Path

from .base import BaseTool, ToolResult


class ResumeWriterTool(BaseTool):
    """Write/generate resume files in various formats."""

    name = "resume_write"
    description = """Write resume content to a file in the specified format.
Supported formats: .md (Markdown), .txt (Plain text), .json (JSON Resume), .html (HTML)
For PDF/DOCX, first write to .md or .html, then convert using bash tool."""
    parameters = {
        "path": {
            "type": "string",
            "description": "Output file path (extension determines format)",
            "required": True,
        },
        "content": {
            "type": "string",
            "description": "Resume content to write (Markdown format recommended)",
            "required": True,
        },
        "template": {
            "type": "string",
            "description": "Template style: 'modern', 'classic', 'minimal', 'creative' (for HTML output)",
            "default": "modern",
        },
    }

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).resolve()
        self._preview_manager = None  # Set by CLI when preview mode is on

    async def execute(self, path: str, content: str, template: str = "modern") -> ToolResult:
        try:
            file_path = self._resolve_path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            suffix = file_path.suffix.lower()

            if suffix == ".md":
                output_content = content
            elif suffix == ".txt":
                output_content = self._to_plain_text(content)
            elif suffix == ".json":
                output_content = self._to_json_resume(content)
            elif suffix == ".html":
                output_content = self._to_html(content, template)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported output format: {suffix}. Supported: .md, .txt, .json, .html",
                )

            # Preview mode: intercept write, but return the same success
            # message as a real write so the LLM continues normally.
            if self._preview_manager is not None:
                self._preview_manager.add(path, output_content, file_path)
                return ToolResult(
                    success=True,
                    output=f"Successfully wrote resume to {path} ({len(output_content)} characters)",
                    data={"preview": True, "pending_path": path, "format": suffix},
                )

            file_path.write_text(output_content, encoding="utf-8")

            return ToolResult(
                success=True,
                output=f"Successfully wrote resume to {path} ({len(output_content)} characters)",
                data={"path": str(file_path), "format": suffix, "size": len(output_content)},
            )

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _to_plain_text(self, content: str) -> str:
        """Convert Markdown to plain text."""
        import re

        text = content
        # Remove markdown headers
        text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
        # Remove bold/italic
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"__(.+?)__", r"\1", text)
        text = re.sub(r"_(.+?)_", r"\1", text)
        # Remove links but keep text
        text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
        # Remove inline code
        text = re.sub(r"`(.+?)`", r"\1", text)

        return text

    def _to_json_resume(self, content: str) -> str:
        """Convert Markdown resume to JSON Resume format."""
        import re

        resume = {
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
        current_section = None

        for i, line in enumerate(lines):
            line = line.strip()

            # First non-empty line is usually the name
            if not resume["basics"]["name"] and line and line.startswith("#"):
                resume["basics"]["name"] = line.lstrip("#").strip()
                continue

            # Detect sections
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

            # Extract email/phone from content
            email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", line)
            if email_match and not resume["basics"]["email"]:
                resume["basics"]["email"] = email_match.group()

            phone_match = re.search(r"[\+]?[\d\-\(\)\s]{10,}", line)
            if phone_match and not resume["basics"]["phone"]:
                resume["basics"]["phone"] = phone_match.group().strip()

        resume["basics"]["summary"] = resume["basics"]["summary"].strip()

        return json.dumps(resume, indent=2, ensure_ascii=False)

    def _to_html(self, content: str, template: str = "modern") -> str:
        """Convert Markdown to HTML with styling."""
        try:
            import markdown

            html_content = markdown.markdown(content, extensions=["tables", "fenced_code"])
        except ImportError:
            # Fallback: basic conversion
            html_content = self._basic_md_to_html(content)

        styles = self._get_template_styles(template)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Resume</title>
    <style>
{styles}
    </style>
</head>
<body>
    <div class="resume-container">
{html_content}
    </div>
</body>
</html>"""
        return html

    def _basic_md_to_html(self, content: str) -> str:
        """Basic Markdown to HTML conversion without library."""
        import re

        html = content
        # Headers
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
        # Bold and italic
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
        # Lists
        html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
        html = re.sub(r"(<li>.*</li>\n)+", r"<ul>\g<0></ul>", html)
        # Paragraphs
        html = re.sub(r"\n\n+", r"</p><p>", html)
        html = f"<p>{html}</p>"
        # Links
        html = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', html)

        return html

    def _get_template_styles(self, template: str) -> str:
        """Get CSS styles for template from external CSS files."""
        try:
            from ..templates import load_template_css

            return load_template_css(template)
        except Exception:
            # Fallback to minimal inline styles if template loading fails
            return """
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

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return self.workspace_dir / p
