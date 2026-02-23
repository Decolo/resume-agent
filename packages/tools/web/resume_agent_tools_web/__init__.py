"""Resume Agent Web Tools - tools for the web/API layer.

Provides:
- UpdateSectionTool: JSON-path based resume section updates
- AnalyzeJDTool: Job description analysis and keyword matching
- ExportResumeTool: Deterministic resume format conversion and export
- WebFetchTool / WebReadTool: Static web content fetching
"""

from .analyze_jd import AnalyzeJDTool
from .export_resume import ExportResumeTool
from .update_section import UpdateSectionTool
from .web_tool import WebFetchTool, WebReadTool

__all__ = [
    "AnalyzeJDTool",
    "ExportResumeTool",
    "UpdateSectionTool",
    "WebFetchTool",
    "WebReadTool",
]
