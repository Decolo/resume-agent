# Phase 1 Quick Reference

Code snippets for core runtime reliability and observability features.

## Retry with Exponential Backoff (`resume_agent/core/retry.py`)

```python
from resume_agent.core.retry import PermanentError, RetryConfig, TransientError, retry_with_backoff

config = RetryConfig(
    max_attempts=3,
    base_delay=1.0,
    max_delay=60.0,
    exponential_base=2.0,
    jitter_factor=0.2,
)


async def fetch_once() -> dict:
    # Raise TransientError for retryable failures
    # Raise PermanentError for failures that should fail fast
    return {"ok": True}


result = await retry_with_backoff(fetch_once, config)
```

## Observability (`resume_agent/core/observability.py`)

```python
from resume_agent.core.observability import AgentObserver

observer = AgentObserver(agent_id="writer", verbose=True)

observer.log_step_start(step=1, user_input="Improve summary")
observer.log_tool_call(
    tool_name="file_read",
    args={"path": "resume.md"},
    result="content...",
    duration_ms=42.5,
    success=True,
    cached=False,
)
observer.log_llm_request(
    model="gemini-2.5-flash",
    tokens=1200,
    cost=0.0008,
    duration_ms=550.0,
    step=1,
)
observer.log_step_end(step=1, duration_ms=640.0)

stats = observer.get_session_stats()
```

## Tool Cache (`resume_agent/core/cache.py`)

```python
from resume_agent.core.cache import ToolCache, get_tool_ttl, should_cache_tool

cache = ToolCache()
tool_name = "file_read"
args = {"path": "resume.md"}

if should_cache_tool(tool_name):
    cached = cache.get(tool_name, args)
    if cached is None:
        fresh = "file content"
        cache.set(tool_name, args, fresh, ttl_seconds=get_tool_ttl(tool_name))
```

## History Management (`resume_agent/core/llm.py`)

```python
from resume_agent.core.llm import HistoryManager
from resume_agent.providers.types import Message, MessagePart

history = HistoryManager(max_messages=50, max_tokens=100000)
history.add_message(Message(role="user", parts=[MessagePart.from_text("Analyze my resume")]))
history.add_message(Message(role="assistant", parts=[MessagePart.from_text("Sure, let's start.")]))

messages = history.get_history()
```

## Pending Tool Approval Flow (`resume_agent/core/llm.py`)

```python
# llm_agent is an instance of LLMAgent (or subclass)
if llm_agent.has_pending_tool_calls():
    pending = llm_agent.list_pending_tool_calls()
    # user decision
    results = await llm_agent.approve_pending_tool_calls()
    # or: rejected_count = llm_agent.reject_pending_tool_calls()
```

## Notes

- Paths and examples in this doc assume the current single-package layout (`resume_agent/*`).
- For CLI command usage, see `docs/README.md` and `README.md`.
