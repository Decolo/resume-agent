"""Observability framework for agent operations - logging, metrics, and tracing."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentEvent:
    """A single event in the agent's execution."""

    timestamp: datetime
    event_type: str  # "tool_call", "llm_request", "error", "step_start", "step_end"
    data: Dict[str, Any]
    duration_ms: Optional[float] = None
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None


class AgentObserver:
    """
    Observability layer for tracking agent execution.

    Collects events, logs, and metrics for debugging and monitoring.
    """

    def __init__(self, agent_id: Optional[str] = None, verbose: bool = False):
        self.events: List[AgentEvent] = []
        self.logger = logging.getLogger("resume_agent")
        self.agent_id = agent_id
        self.verbose = verbose
        self._setup_logging()

    def _format_agent_prefix(self, agent_id: Optional[str]) -> str:
        use_id = agent_id or self.agent_id
        return f"[{use_id}] " if use_id else ""

    def _setup_logging(self):
        """Configure logging format and handlers."""
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO if self.verbose else logging.WARNING)

    def log_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: str,
        duration_ms: float,
        success: bool = True,
        cached: bool = False,
        agent_id: Optional[str] = None,
    ):
        """
        Log a tool execution.

        Args:
            tool_name: Name of the tool executed
            args: Arguments passed to the tool
            result: Result from tool execution
            duration_ms: Execution time in milliseconds
            success: Whether execution succeeded
            cached: Whether result was from cache
        """
        event = AgentEvent(
            timestamp=datetime.now(),
            event_type="tool_call",
            data={
                "tool": tool_name,
                "args": args,
                "result": result[:200],  # Truncate for logging
                "success": success,
                "cached": cached,
            },
            duration_ms=duration_ms,
        )
        self.events.append(event)

        # Log to console
        prefix = self._format_agent_prefix(agent_id)
        cache_indicator = " [CACHED]" if cached else ""
        status = "✓" if success else "✗"
        self.logger.info(f"{prefix}{status} Tool: {tool_name}{cache_indicator} ({duration_ms:.2f}ms)")

    def log_llm_request(
        self,
        model: str,
        tokens: int,
        cost: float,
        duration_ms: float,
        step: int,
        agent_id: Optional[str] = None,
    ):
        """
        Log an LLM API request.

        Args:
            model: Model name (e.g., "gemini-2.5-flash")
            tokens: Total tokens used (input + output)
            cost: Estimated cost in USD
            duration_ms: Request duration in milliseconds
            step: Current step number in agent loop
        """
        event = AgentEvent(
            timestamp=datetime.now(),
            event_type="llm_request",
            data={"model": model, "step": step},
            duration_ms=duration_ms,
            tokens_used=tokens,
            cost_usd=cost,
        )
        self.events.append(event)

        prefix = self._format_agent_prefix(agent_id)
        self.logger.info(f"{prefix}🤖 LLM: {model} | Step {step} | {tokens} tokens | ${cost:.4f} | {duration_ms:.2f}ms")

    def log_llm_response(
        self,
        step: int,
        text: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        agent_id: Optional[str] = None,
    ):
        """Log the LLM response details (text + tool calls)."""
        event = AgentEvent(
            timestamp=datetime.now(),
            event_type="llm_response",
            data={
                "step": step,
                "text": text,
                "tool_calls": tool_calls or [],
            },
        )
        self.events.append(event)

        prefix = self._format_agent_prefix(agent_id)
        tools = tool_calls or []
        try:
            import json as _json

            tools_dump = _json.dumps(tools, ensure_ascii=True)
        except Exception:
            tools_dump = str(tools)

        self.logger.info(f"{prefix}🧠 LLM response | Step {step}")
        self.logger.info(f"{prefix}↳ tools={tools_dump}")
        self.logger.info(f"{prefix}↳ text={text}")

    def log_error(
        self,
        error_type: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
    ):
        """
        Log an error event.

        Args:
            error_type: Type of error (e.g., "tool_execution", "llm_api")
            message: Error message
            context: Additional context about the error
        """
        event = AgentEvent(
            timestamp=datetime.now(),
            event_type="error",
            data={"error_type": error_type, "message": message, "context": context or {}},
        )
        self.events.append(event)

        prefix = self._format_agent_prefix(agent_id)
        self.logger.error(f"{prefix}❌ Error ({error_type}): {message}")

    def log_step_start(self, step: int, user_input: Optional[str] = None, agent_id: Optional[str] = None):
        """
        Log the start of an agent step.

        Args:
            step: Step number
            user_input: User input for this step (if applicable)
        """
        event = AgentEvent(
            timestamp=datetime.now(),
            event_type="step_start",
            data={"step": step, "user_input": user_input[:100] if user_input else None},
        )
        self.events.append(event)

        prefix = self._format_agent_prefix(agent_id)
        if step == 1 and user_input:
            self.logger.info(f"{prefix}👤 User: {user_input[:100]}...")
        self.logger.info(f"{prefix}🔄 Step {step} started")

    def log_step_end(self, step: int, duration_ms: float, agent_id: Optional[str] = None):
        """
        Log the end of an agent step.

        Args:
            step: Step number
            duration_ms: Step duration in milliseconds
        """
        event = AgentEvent(
            timestamp=datetime.now(), event_type="step_end", data={"step": step}, duration_ms=duration_ms
        )
        self.events.append(event)

        prefix = self._format_agent_prefix(agent_id)
        self.logger.info(f"{prefix}✓ Step {step} completed ({duration_ms:.2f}ms)")

    def get_session_stats(self) -> Dict[str, Any]:
        """
        Get aggregated statistics for the current session.

        Returns:
            Dictionary with session statistics
        """
        total_tokens = sum(e.tokens_used or 0 for e in self.events)
        total_cost = sum(e.cost_usd or 0 for e in self.events)
        total_duration = sum(e.duration_ms or 0 for e in self.events)

        tool_calls = [e for e in self.events if e.event_type == "tool_call"]
        llm_requests = [e for e in self.events if e.event_type == "llm_request"]
        errors = [e for e in self.events if e.event_type == "error"]

        # Count cached vs non-cached tool calls
        cached_calls = sum(1 for e in tool_calls if e.data.get("cached", False))
        cache_hit_rate = cached_calls / len(tool_calls) if tool_calls else 0.0

        return {
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost,
            "total_duration_ms": total_duration,
            "event_count": len(self.events),
            "tool_calls": len(tool_calls),
            "llm_requests": len(llm_requests),
            "errors": len(errors),
            "cache_hit_rate": cache_hit_rate,
        }

    def print_session_summary(self):
        """Print a formatted summary of the session."""
        stats = self.get_session_stats()

        print("\n" + "=" * 60)
        print("SESSION SUMMARY")
        print("=" * 60)
        print(f"Total Events:     {stats['event_count']}")
        print(f"Tool Calls:       {stats['tool_calls']} (cache hit: {stats['cache_hit_rate']:.1%})")
        print(f"LLM Requests:     {stats['llm_requests']}")
        print(f"Errors:           {stats['errors']}")
        print(f"Total Tokens:     {stats['total_tokens']:,}")
        print(f"Total Cost:       ${stats['total_cost_usd']:.4f}")
        print(f"Total Duration:   {stats['total_duration_ms']:.2f}ms")
        print("=" * 60 + "\n")

    def clear(self):
        """Clear all recorded events."""
        self.events.clear()
        self.logger.info("Observer events cleared")
