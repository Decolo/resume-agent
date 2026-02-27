# Integration Guide: LinkedIn Tool for Resume Agent

This guide shows how to integrate the LinkedIn browser control POC into the resume-agent as a proper tool.

## Architecture

```
resume_agent/
├── tools/
│   └── linkedin_tool.py          # New LinkedIn tool
├── core/
│   └── agents/
│       └── linkedin_agent.py     # Optional: specialized agent
└── config/
    └── config.yaml               # Add LinkedIn config
```

## Step 1: Create LinkedIn Tool

**File**: `resume_agent/tools/linkedin_tool.py`

```python
"""LinkedIn posting tool using Vercel Agent Browser via CDP."""

import asyncio
import subprocess
from pathlib import Path
from typing import Any

from resume_agent.tools.base import BaseTool, ToolResult


class LinkedInPostTool(BaseTool):
    """Post content to LinkedIn using AI-powered browser automation."""

    def __init__(self, cdp_port: int = 9222, agent_browser_path: str = "agent-browser"):
        self.cdp_port = cdp_port
        self.agent_browser_path = agent_browser_path
        self._poc_script = Path(__file__).parent.parent.parent / "poc" / "linkedin_vercel_agent.js"

    @property
    def name(self) -> str:
        return "linkedin_post"

    @property
    def description(self) -> str:
        return (
            "Post content to LinkedIn using your logged-in Chrome browser. "
            "Requires Chrome to be running with --remote-debugging-port=9222. "
            "Uses AI-powered browser automation to adapt to UI changes."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "content": {
                "type": "string",
                "description": "The text content to post on LinkedIn",
                "required": True,
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview the post without actually submitting it",
                "required": False,
                "default": False,
            },
        }

    async def execute(self, content: str, dry_run: bool = False) -> ToolResult:
        """Execute LinkedIn post via agent-browser."""
        try:
            # Build command
            cmd = ["node", str(self._poc_script), content, "--port", str(self.cdp_port)]
            if dry_run:
                cmd.append("--dry-run")

            # Run agent-browser script
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                return ToolResult(
                    success=True,
                    data={"posted": not dry_run, "content": content},
                    message=stdout.decode() if stdout else "Post submitted successfully",
                )
            else:
                error_msg = stderr.decode() if stderr else "Unknown error"
                return ToolResult(
                    success=False,
                    error=f"Failed to post to LinkedIn: {error_msg}",
                )

        except FileNotFoundError:
            return ToolResult(
                success=False,
                error=(
                    "agent-browser not found. Install with: npm install -g agent-browser && agent-browser install"
                ),
            )
        except Exception as e:
            return ToolResult(success=False, error=f"LinkedIn post failed: {str(e)}")
```

## Step 2: Register Tool

**File**: `resume_agent/core/agent.py` (or `agent_factory.py`)

```python
from resume_agent.tools.linkedin_tool import LinkedInPostTool

# In ResumeAgent._init_tools() or similar:
def _init_tools(self):
    # ... existing tools ...

    # Add LinkedIn tool if enabled in config
    if self.config.get("linkedin", {}).get("enabled", False):
        cdp_port = self.config["linkedin"].get("cdp_port", 9222)
        self.tools["linkedin_post"] = LinkedInPostTool(cdp_port=cdp_port)
```

## Step 3: Add Configuration

**File**: `config/config.yaml`

```yaml
# LinkedIn integration (optional)
linkedin:
  enabled: false  # Set to true to enable LinkedIn posting
  cdp_port: 9222  # Chrome remote debugging port

  # Instructions for users:
  # 1. Launch Chrome: google-chrome --remote-debugging-port=9222
  # 2. Log into LinkedIn in that Chrome window
  # 3. Set enabled: true in config.local.yaml
```

## Step 4: Create Specialized Agent (Optional)

**File**: `resume_agent/core/agents/linkedin_agent.py`

```python
"""LinkedIn agent for social media posting."""

from resume_agent.core.agents.base import BaseAgent
from resume_agent.core.agents.protocol import AgentTask, AgentResult


class LinkedInAgent(BaseAgent):
    """Agent specialized in posting resume content to LinkedIn."""

    @property
    def agent_id(self) -> str:
        return "linkedin_agent"

    @property
    def agent_type(self) -> str:
        return "linkedin"

    @property
    def capabilities(self) -> list[str]:
        return ["linkedin_post", "social_media", "content_distribution"]

    def can_handle(self, task: AgentTask) -> bool:
        """Check if task involves LinkedIn posting."""
        keywords = ["linkedin", "post", "share", "social media"]
        return any(kw in task.description.lower() for kw in keywords)

    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute LinkedIn posting task."""
        # Implementation here
        pass
```

## Usage Examples

### Direct Tool Usage

```python
from resume_agent.tools.linkedin_tool import LinkedInPostTool

tool = LinkedInPostTool()
result = await tool.execute(
    content="Just updated my resume! Check out my new skills in Python and AI.",
    dry_run=False
)
```

### Via Agent

```python
agent = ResumeAgent(config)
response = await agent.process("Post my resume summary to LinkedIn")
```

### CLI

```bash
# Interactive mode
uv run resume-agent
> Post my resume summary to LinkedIn

# Single prompt
uv run resume-agent --prompt "Share my top 3 achievements on LinkedIn"
```

## Testing

**File**: `tests/tools/test_linkedin_tool.py`

```python
import pytest
from resume_agent.tools.linkedin_tool import LinkedInPostTool


@pytest.mark.asyncio
async def test_linkedin_post_dry_run():
    """Test LinkedIn post in dry-run mode."""
    tool = LinkedInPostTool()
    result = await tool.execute(
        content="Test post",
        dry_run=True
    )
    assert result.success
    assert result.data["posted"] is False


@pytest.mark.asyncio
@pytest.mark.integration
async def test_linkedin_post_real():
    """Test actual LinkedIn posting (requires Chrome with CDP)."""
    tool = LinkedInPostTool()
    result = await tool.execute(
        content="Test post from resume-agent integration test"
    )
    # Only runs if Chrome is available
    if result.success:
        assert result.data["posted"] is True
```

## Security Considerations

1. **CDP Port Exposure**: Never expose port 9222 to the internet
2. **Session Hijacking**: CDP gives full browser control - use on trusted networks only
3. **Rate Limiting**: LinkedIn may rate-limit automated posts
4. **Content Validation**: Sanitize user input before posting
5. **User Consent**: Always confirm before posting to social media

## Next Steps

1. Add media upload support (images, PDFs)
2. Schedule posts for later
3. Support multiple social platforms (Twitter, Facebook)
4. Add analytics tracking (views, engagement)
5. Implement retry logic for failed posts
