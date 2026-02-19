"""Quick Reference Guide for Phase 1 Improvements"""

# RETRY LOGIC (packages/core/resume_agent_core/retry.py)
# ====================================

from packages.core.resume_agent_core.retry import RetryConfig, retry_with_backoff, TransientError, PermanentError

# Configure retry behavior
config = RetryConfig(
    max_attempts=3,           # Number of retry attempts
    base_delay=1.0,           # Initial delay in seconds
    max_delay=60.0,           # Maximum delay cap
    exponential_base=2.0,     # Exponential growth factor
    jitter_factor=0.2         # ±20% random variation
)

# Use with async functions
async def make_request():
    return await retry_with_backoff(some_async_func, config)

# Classify errors
try:
    raise TransientError("Temporary failure")  # Will retry
except TransientError:
    pass

try:
    raise PermanentError("Auth failed")  # Won't retry
except PermanentError:
    pass


# OBSERVABILITY (packages/core/resume_agent_core/observability.py)
# ==============================================

from packages.core.resume_agent_core.observability import AgentObserver, AgentEvent

observer = AgentObserver()

# Log tool execution
observer.log_tool_call(
    tool_name="file_read",
    args={"path": "resume.pdf"},
    result="File content...",
    duration_ms=150.5,
    success=True,
    cached=False
)

# Log LLM request
observer.log_llm_request(
    model="gemini-2.0-flash",
    tokens=1000,
    cost=0.08,
    duration_ms=500.0,
    step=1
)

# Log errors
observer.log_error(
    error_type="tool_execution",
    message="File not found",
    context={"tool": "file_read"}
)

# Get session statistics
stats = observer.get_session_stats()
print(f"Total tokens: {stats['total_tokens']}")
print(f"Total cost: ${stats['total_cost_usd']:.4f}")
print(f"Cache hit rate: {stats['cache_hit_rate']:.1%}")

# Print formatted summary
observer.print_session_summary()


# CACHING (packages/core/resume_agent_core/cache.py)
# ===============================

from packages.core.resume_agent_core.cache import ToolCache, should_cache_tool, get_tool_ttl

cache = ToolCache()

# Check if tool should be cached
if should_cache_tool("file_read"):
    # Get TTL for tool
    ttl = get_tool_ttl("file_read")  # Returns 60 seconds

    # Try to get from cache
    result = cache.get("file_read", {"path": "resume.pdf"})

    if result is None:
        # Cache miss - execute tool
        result = execute_tool()

        # Store in cache
        cache.set("file_read", {"path": "resume.pdf"}, result, ttl_seconds=ttl)

# Get cache statistics
stats = cache.get_stats()
print(f"Cache hits: {stats['hits']}")
print(f"Cache misses: {stats['misses']}")
print(f"Hit rate: {stats['hit_rate']:.1%}")

# Print formatted stats
cache.print_stats()


# HISTORY MANAGEMENT (packages/core/resume_agent_core/llm.py)
# ========================================

from packages.core.resume_agent_core.llm import HistoryManager
from packages.providers.resume_agent_providers.types import Message, MessagePart

manager = HistoryManager(
    max_messages=50,      # Keep last 50 messages
    max_tokens=100000     # Keep under 100k tokens
)

# Add message (automatically prunes if needed)
msg = Message(
    role="user",
    parts=[MessagePart.from_text(text="Hello")]
)
manager.add_message(msg)

# Get current history
history = manager.get_history()

# Clear history
manager.clear()


# TOOL RESULT METADATA (packages/core/resume_agent_core/tools/base.py)
# ================================================

from packages.core.resume_agent_core.tools.base import ToolResult

result = ToolResult(
    success=True,
    output="File content",
    error=None,
    data={"path": "/path/to/file"},
    # Phase 1 additions:
    execution_time_ms=150.5,
    tokens_used=100,
    cached=False,
    retry_count=0
)

# Convert to message
message = result.to_message()


# FILE TOOL SECURITY (packages/core/resume_agent_core/tools/file_tool.py)
# ===================================================

from packages.core.resume_agent_core.tools.file_tool import FileReadTool, MAX_FILE_SIZE

tool = FileReadTool(workspace_dir=".")

# Automatically validates:
# - File size (max 10MB)
# - Binary file detection (checks for null bytes)
result = await tool.execute("resume.pdf")

if not result.success:
    print(f"Error: {result.error}")


# BASH TOOL SECURITY (packages/core/resume_agent_core/tools/bash_tool.py)
# ==================================================

from packages.core.resume_agent_core.tools.bash_tool import BashTool

tool = BashTool()

# Automatically validates:
# - Blocked commands: rm, dd, mkfs, sudo, curl, etc.
# - Dangerous patterns: ;, &&, ||, |, `, $(, ${, >, >>, 2>, <
result = await tool.execute("ls -la")

if not result.success:
    print(f"Error: {result.error}")


# RESUME PARSER CACHING (packages/core/resume_agent_core/tools/resume_parser.py)
# ==========================================================

from packages.core.resume_agent_core.tools.resume_parser import ResumeParserTool

tool = ResumeParserTool(workspace_dir=".")

# First call: parses file
result1 = await tool.execute("resume.pdf")

# Second call (file unchanged): returns cached result
result2 = await tool.execute("resume.pdf")
print(f"Cached: {result2.cached}")  # True

# File modified: cache invalidated, re-parses
# (mtime changed, so cache miss)


# INTEGRATION IN LLM AGENT (packages/core/resume_agent_core/llm.py)
# ================================================================

from packages.core.resume_agent_core.llm import LLMAgent, LLMConfig

config = LLMConfig(
    api_key="your-api-key",
    model="gemini-2.0-flash"
)

agent = LLMAgent(config)

# Automatically initialized:
# - agent.history_manager (HistoryManager)
# - agent.observer (AgentObserver)
# - agent.cache (ToolCache)

# Run agent (uses all Phase 1 improvements)
result = await agent.run("Analyze my resume")

# Prints session summary and cache stats automatically
