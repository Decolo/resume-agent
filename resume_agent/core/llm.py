"""LLM client and history management."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from resume_agent.providers import create_provider
from resume_agent.providers.types import (
    FunctionCall,
    FunctionResponse,
    GenerationConfig,
    LLMResponse,
    Message,
    MessagePart,
    StreamDelta,
    ToolSchema,
)

from .cache import ToolCache, get_tool_ttl, should_cache_tool
from .observability import AgentObserver
from .retry import RetryConfig, TransientError, retry_with_backoff


class HistoryManager:
    """Manages conversation history with automatic pruning."""

    def __init__(self, max_messages: int = 50, max_tokens: int = 100000):
        """
        Initialize history manager.

        Args:
            max_messages: Maximum number of messages to keep
            max_tokens: Estimated maximum tokens to keep
        """
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self._history: List[Message] = []

    def add_message(self, message: Message, allow_incomplete: bool = False):
        """Add a message and prune if needed.

        If allow_incomplete is True, skips validation/pruning to allow a
        model function_call to be immediately followed by its tool response.
        """
        if message is None:
            return
        self._history.append(message)
        if allow_incomplete:
            return
        self._ensure_valid_sequence()
        self._prune_if_needed()

    def get_history(self) -> List[Message]:
        """Get current history."""
        return self._history

    def clear(self):
        """Clear all history."""
        self._history.clear()

    def _prune_if_needed(self):
        """Prune history if it exceeds limits while preserving function call/response pairs."""
        # Message count pruning
        if len(self._history) > self.max_messages:
            # Keep recent messages (sliding window)
            self._history = self._history[-self.max_messages :]
            # After sliding window, ensure we didn't break pairs
            self._fix_broken_pairs()
            self._ensure_valid_sequence()

        # Token-based pruning (rough estimate)
        estimated_tokens = sum(self._estimate_tokens(msg) for msg in self._history)
        if estimated_tokens > self.max_tokens:
            # Remove oldest messages until under limit, respecting pairs
            while estimated_tokens > self.max_tokens and len(self._history) > 2:
                # Check if first message is part of a function call/response pair
                if self._is_function_call_pair(0):
                    # Remove both messages in the pair
                    removed1 = self._history.pop(0)
                    removed2 = self._history.pop(0)
                    estimated_tokens -= self._estimate_tokens(removed1)
                    estimated_tokens -= self._estimate_tokens(removed2)
                else:
                    # Safe to remove single message
                    removed = self._history.pop(0)
                    estimated_tokens -= self._estimate_tokens(removed)
            self._ensure_valid_sequence()

    def _is_function_call_pair(self, index: int) -> bool:
        """
        Check if message at index is the first part of a function call/response pair.

        A valid pair is:
        - history[index] has role="assistant" with function_call parts
        - history[index+1] has role="tool" with function_response parts
        """
        if index >= len(self._history) - 1:
            return False

        msg1 = self._history[index]
        msg2 = self._history[index + 1]
        if msg1 is None or msg2 is None:
            return False

        has_function_call = self._has_function_call(msg1)

        has_function_response = self._has_function_response(msg2)

        return has_function_call and has_function_response

    def _fix_broken_pairs(self):
        """
        Fix broken function call/response pairs after pruning.

        If history starts with an orphaned function response (tool message with
        function_response but no preceding function_call), remove it.
        """
        if not self._history:
            return

        # Drop any None entries that might exist
        while self._history and self._history[0] is None:
            self._history.pop(0)
        while self._history and self._history[-1] is None:
            self._history.pop()

        # Check if first message is an orphaned function response
        first_msg = self._history[0]
        if (
            first_msg.role == "tool"
            and first_msg.parts is not None
            and any(part.function_response for part in first_msg.parts)
        ):
            # This is an orphaned response, remove it
            self._history.pop(0)

        # Check if last message is an orphaned function call
        if self._history:
            last_msg = self._history[-1]
            if (
                last_msg.role == "assistant"
                and last_msg.parts is not None
                and any(part.function_call for part in last_msg.parts)
            ):
                # This is an orphaned call, remove it
                self._history.pop()

    def _has_function_call(self, msg: Message) -> bool:
        return (
            msg is not None
            and msg.role == "assistant"
            and msg.parts is not None
            and any(part.function_call for part in msg.parts)
        )

    def _has_function_response(self, msg: Message) -> bool:
        return (
            msg is not None
            and msg.role == "tool"
            and msg.parts is not None
            and any(part.function_response for part in msg.parts)
        )

    def _ensure_valid_sequence(self):
        """Ensure history ordering is valid for tool calling."""
        if not self._history:
            return

        # Remove None entries
        self._history = [m for m in self._history if m is not None]
        if not self._history:
            return

        cleaned: List[Message] = []
        for msg in self._history:
            # Drop orphaned function responses
            if self._has_function_response(msg):
                if not cleaned:
                    continue
                if not self._has_function_call(cleaned[-1]):
                    continue
            # Drop assistant function calls that do not follow a user turn
            if self._has_function_call(msg):
                # Allow a leading assistant tool call when history was truncated;
                # the second pass still drops it if no matching tool response.
                if cleaned and cleaned[-1].role not in {"user", "tool"}:
                    continue
            cleaned.append(msg)

        # Drop assistant function calls not followed by a tool response
        final: List[Message] = []
        i = 0
        while i < len(cleaned):
            msg = cleaned[i]
            if self._has_function_call(msg):
                if i + 1 >= len(cleaned):
                    i += 1
                    continue
                next_msg = cleaned[i + 1]
                if not self._has_function_response(next_msg):
                    i += 1
                    continue
            final.append(msg)
            i += 1

        self._history = final

    def _estimate_tokens(self, message: Message) -> int:
        """
        Estimate token count for a message.

        Uses rough heuristic: 1 token ≈ 4 characters
        """
        if message is None or message.parts is None:
            return 0
        total_chars = 0
        for part in message.parts:
            if part.text:
                total_chars += len(part.text)
            elif part.function_call:
                total_chars += len(part.function_call.name) * 2
                if part.function_call.arguments:
                    total_chars += len(str(dict(part.function_call.arguments)))
            elif part.function_response:
                total_chars += len(part.function_response.name) * 2
                if part.function_response.response:
                    total_chars += len(str(part.function_response.response))

        return total_chars // 4  # Rough estimate: 4 chars per token


@dataclass
class LLMConfig:
    """Configuration for LLM client."""

    api_key: str
    provider: str = "gemini"
    model: str = "gemini-2.0-flash"
    max_tokens: int = 4096
    temperature: float = 0.7
    api_base: str = ""  # Custom API endpoint (proxy)
    search_grounding: bool = False


class LLMAgent:
    """Provider-agnostic LLM agent with tool calling."""

    _COST_PER_MILLION_TOKENS = 0.08
    _READ_ONLY_TOOLS = {
        "file_read",
        "file_list",
        "resume_parse",
        "web_fetch",
        "web_read",
        "lint_resume",
        "job_match",
        "resume_validate",
    }
    # Loop-guard thresholds (tune as needed)
    _MAX_TOOL_ONLY_STEPS = 8
    _MAX_REPEAT_READ_ONLY = 2
    _MAX_REPEAT_DEFAULT = 1
    _WRITE_TOOLS = {"file_write", "resume_write", "file_rename"}
    _JOB_SEARCH_TOOL = "job_search"
    _JOB_DETAIL_TOOL = "job_detail"
    _JOB_DETAIL_CONFLICT_REASON = (
        "Rejected by policy: job_detail cannot run in the same step as job_search. "
        "Use job_search for discovery, then call job_detail in a later step with an explicit LinkedIn job_url."
    )

    def __init__(
        self,
        config: LLMConfig,
        system_prompt: str = "",
        agent_id: Optional[str] = None,
        session_manager: Optional[Any] = None,
        verbose: bool = False,
    ):
        self.config = config
        self.system_prompt = system_prompt
        self.agent_id = agent_id
        self.verbose = verbose

        # Initialize provider
        self.provider = create_provider(
            provider=self.config.provider,
            api_key=self.config.api_key,
            model=self.config.model,
            api_base=self.config.api_base,
            search_grounding=self.config.search_grounding,
        )

        # Tools registry: name -> (function, schema)
        self._tools: Dict[str, tuple] = {}

        # History manager with automatic pruning
        self.history_manager = HistoryManager(max_messages=50, max_tokens=100000)

        # Observability for logging and metrics
        self.observer = AgentObserver(agent_id=agent_id, verbose=verbose)

        # Tool result caching
        self.cache = ToolCache()

        # Session management
        self.session_manager = session_manager
        self.current_session_id: Optional[str] = None

        # Retry configuration for LLM calls (defaults match RetryConfig dataclass)
        self._retry_config = RetryConfig()
        # Pending tool calls that require user approval
        self._pending_tool_calls: List[FunctionCall] = []
        # Auto-approve tool calls that require approval
        self._auto_approve_tools = False

        # Pluggable hooks for API integration
        self._approval_handler: Optional[Callable] = None  # async (function_calls) → (approved_calls, rejection_reason)
        self._tool_event_handler: Optional[Callable] = None  # async (event_type, tool_name, args, result?, success?)
        self._interrupt_checker: Optional[Callable] = None  # async () → bool

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        func: Callable,
    ):
        """Register a tool that the agent can use."""
        schema = ToolSchema(name=name, description=description, parameters=parameters)
        self._tools[name] = (func, schema)

    def _get_tools(self) -> Optional[List[ToolSchema]]:
        if not self._tools:
            return None
        return [schema for _, (_, schema) in self._tools.items()]

    async def run(
        self,
        user_input: str,
        max_steps: int = 20,
        stream: bool = False,
        on_stream_delta: Optional[Callable[[StreamDelta], None]] = None,
    ) -> str:
        """Run the agent with user input, handling tool calls automatically."""
        # If we already have pending tool calls, ask for approval first
        if self._pending_tool_calls:
            return "Pending tool call(s) require approval. Use /approve or /reject."

        # Add user message to history
        self.history_manager.add_message(Message.user(user_input))

        # Ensure history ordering is valid before calling the model
        self.history_manager._ensure_valid_sequence()

        loop_state: Dict[str, Any] = {
            "last_call": None,
            "same_call_repeats": 0,
            "tool_only_steps": 0,
            "last_result": None,
        }

        for step in range(1, max_steps + 1):
            # Check for interrupt before each step
            if self._interrupt_checker and await self._interrupt_checker():
                raise asyncio.CancelledError("Run interrupted")

            self.observer.log_step_start(
                step,
                user_input if step == 1 else None,
                agent_id=self.agent_id,
            )
            start_time = time.time()

            # 1. Call LLM
            try:
                if stream:
                    response = await self._call_llm_stream(on_stream_delta=on_stream_delta)
                else:
                    response = await self._call_llm()
            except asyncio.CancelledError:
                # Allow user-initiated interruption to bubble up
                raise
            except Exception as e:
                self.observer.log_error(
                    error_type="llm_request",
                    message=str(e),
                    context={"model": self.config.model, "step": step},
                    agent_id=self.agent_id,
                )
                return f"Error: LLM request failed: {e}"

            # 2. Log LLM metrics
            self._log_llm_metrics(step, start_time, response.usage)

            # 3. Parse response
            function_calls, text_parts = self._parse_response(response)
            response_text = " ".join(text_parts).strip()

            # 4. Log response summary
            tool_calls_dump = []
            if function_calls:
                for fc in function_calls:
                    tool_calls_dump.append(
                        {
                            "name": fc.name,
                            "args": dict(fc.arguments) if fc.arguments else {},
                        }
                    )
            self.observer.log_llm_response(
                step=step,
                text=response_text or "(no text)",
                tool_calls=tool_calls_dump,
                agent_id=self.agent_id,
            )

            # 5. Add model response to history
            assistant_parts: List[MessagePart] = []
            if response_text:
                assistant_parts.append(MessagePart.from_text(response_text))
            for fc in function_calls:
                assistant_parts.append(MessagePart.from_function_call(fc))
            if assistant_parts:
                self.history_manager.add_message(
                    Message(role="assistant", parts=assistant_parts),
                    allow_incomplete=bool(function_calls),
                )

            # 6. If no tool calls → done
            if not function_calls:
                step_duration = (time.time() - start_time) * 1000
                self.observer.log_step_end(step, step_duration, agent_id=self.agent_id)
                if self.verbose:
                    self.observer.print_session_summary()
                    self.cache.print_stats()
                return response_text

            # 7. Apply tool policy filters before execution / approval flow.
            function_calls, policy_responses = self._apply_tool_call_policy(function_calls)

            # If all calls were rejected by policy, record rejections and continue.
            if not function_calls and policy_responses:
                tool_message = Message(
                    role="tool",
                    parts=[MessagePart.from_function_response(fr) for fr in policy_responses],
                )
                self.history_manager.add_message(tool_message)
                if self.session_manager:
                    await self._auto_save()
                step_duration = (time.time() - start_time) * 1000
                self.observer.log_step_end(step, step_duration, agent_id=self.agent_id)
                continue

            # 8. Pause before executing any write tools (approval required)
            if self._requires_tool_approval(function_calls) and not self._auto_approve_tools:
                if self._approval_handler:
                    # API mode: delegate to approval handler
                    approved, rejection = await self._approval_handler(function_calls)
                    if not approved:
                        # Write rejection result into history so LLM knows it was rejected
                        tool_message = Message(
                            role="tool",
                            parts=[
                                MessagePart.from_function_response(
                                    FunctionResponse(
                                        name=fc.name,
                                        response={"result": f"Rejected: {rejection}"},
                                        call_id=fc.id,
                                    )
                                )
                                for fc in function_calls
                            ],
                        )
                        self.history_manager.add_message(tool_message)
                        continue
                    function_calls = approved
                else:
                    # CLI mode: pause and wait for /approve
                    self._pending_tool_calls = list(function_calls)
                    step_duration = (time.time() - start_time) * 1000
                    self.observer.log_step_end(step, step_duration, agent_id=self.agent_id)
                    return "Tool call(s) require approval before execution. Use /approve or /reject."

            # 9. Loop guard to prevent runaway tool-only loops
            guard_reason = self._check_loop_guard(function_calls, response_text, loop_state)
            if guard_reason:
                step_duration = (time.time() - start_time) * 1000
                self.observer.log_error(
                    error_type="loop_guard",
                    message=guard_reason,
                    context={
                        "last_call": loop_state.get("last_call"),
                        "tool_only_steps": loop_state.get("tool_only_steps"),
                        "same_call_repeats": loop_state.get("same_call_repeats"),
                    },
                    agent_id=self.agent_id,
                )
                self.observer.log_step_end(step, step_duration, agent_id=self.agent_id)
                return guard_reason

            # 10. Execute tools in parallel
            executed_responses = await asyncio.gather(
                *[self._execute_tool(fc) for fc in function_calls],
                return_exceptions=False,
            )
            function_responses = [*policy_responses, *executed_responses]

            # 11. Capture last tool result for fallback
            if len(function_calls) == 1 and executed_responses:
                fr = executed_responses[0]
                if fr and fr.response:
                    loop_state["last_result"] = fr.response.get("result")

            # 12. Update history + auto-save
            tool_message = Message(
                role="tool",
                parts=[MessagePart.from_function_response(fr) for fr in function_responses],
            )
            self.history_manager.add_message(tool_message)
            if self.session_manager:
                await self._auto_save()

            # 13. Log step end
            step_duration = (time.time() - start_time) * 1000
            self.observer.log_step_end(step, step_duration, agent_id=self.agent_id)

        return f"Max steps ({max_steps}) reached."

    # --- Extracted helper methods ---

    async def _call_llm(self) -> LLMResponse:
        """Call LLM with retry logic."""

        async def make_request():
            messages = list(self.history_manager.get_history())
            return await self.provider.generate(
                messages=messages,
                tools=self._get_tools(),
                config=self._build_generation_config(),
            )

        return await retry_with_backoff(make_request, self._retry_config)

    async def _call_llm_stream(self, on_stream_delta: Optional[Callable[[StreamDelta], None]] = None) -> LLMResponse:
        """Call LLM with streaming and aggregate into a final response."""
        text_chunks: List[str] = []
        accumulated_text = ""
        function_calls_map: Dict[str, FunctionCall] = {}
        function_call_order: List[str] = []
        arg_buffers: Dict[str, str] = {}
        last_call_key: Optional[str] = None
        transient_counter = 0

        async for delta in self.provider.generate_stream(
            messages=list(self.history_manager.get_history()),
            tools=self._get_tools(),
            config=self._build_generation_config(),
        ):
            normalized_text = ""
            if delta.text:
                normalized_text = self._normalize_stream_text_delta(accumulated_text, delta.text)
                if normalized_text:
                    accumulated_text += normalized_text
                    text_chunks.append(normalized_text)

            callback_delta: Optional[StreamDelta] = None
            if on_stream_delta:
                callback_delta = StreamDelta(
                    text=normalized_text if delta.text is not None else None,
                    function_call_start=delta.function_call_start,
                    function_call_delta=delta.function_call_delta,
                    function_call_id=delta.function_call_id,
                    function_call_index=delta.function_call_index,
                    function_call_end=delta.function_call_end,
                    finish_reason=delta.finish_reason,
                    usage=delta.usage,
                )
                has_callback_payload = bool(
                    callback_delta.text
                    or callback_delta.function_call_start
                    or callback_delta.function_call_delta
                    or callback_delta.function_call_end
                    or callback_delta.finish_reason
                    or callback_delta.usage
                )
                if has_callback_payload:
                    if asyncio.iscoroutinefunction(on_stream_delta):
                        await on_stream_delta(callback_delta)
                    else:
                        on_stream_delta(callback_delta)

            if delta.function_call_start:
                call = delta.function_call_start
                if call.id:
                    call_key = f"id:{call.id}"
                elif delta.function_call_id:
                    call_key = f"id:{delta.function_call_id}"
                elif delta.function_call_index is not None:
                    call_key = f"idx:{delta.function_call_index}"
                else:
                    transient_counter += 1
                    call_key = f"stream:{transient_counter}"

                call_id = (
                    call.id or delta.function_call_id or f"tool_{int(time.time() * 1000)}_{len(function_call_order)}"
                )

                if call_key not in function_calls_map:
                    function_calls_map[call_key] = FunctionCall(name=call.name, arguments={}, id=call_id)
                    function_call_order.append(call_key)
                else:
                    existing_call = function_calls_map[call_key]
                    if not existing_call.name and call.name:
                        existing_call.name = call.name
                    if not existing_call.id:
                        existing_call.id = call_id

                arg_buffers.setdefault(call_key, "")
                last_call_key = call_key

            if delta.function_call_delta:
                if delta.function_call_id:
                    call_key = f"id:{delta.function_call_id}"
                elif delta.function_call_index is not None:
                    call_key = f"idx:{delta.function_call_index}"
                else:
                    call_key = last_call_key

                if not call_key:
                    transient_counter += 1
                    call_key = f"stream:{transient_counter}"

                if call_key not in function_calls_map:
                    transient_counter += 1
                    generated_id = (
                        delta.function_call_id or f"tool_stream_{int(time.time() * 1000)}_{transient_counter}"
                    )
                    function_calls_map[call_key] = FunctionCall(name="", arguments={}, id=generated_id)
                    function_call_order.append(call_key)

                # Normalize argument chunks because some providers emit cumulative
                # snapshots instead of incremental deltas.
                prior_args = arg_buffers.get(call_key, "")
                normalized_args_delta = self._normalize_stream_text_delta(prior_args, delta.function_call_delta)
                if normalized_args_delta:
                    arg_buffers[call_key] = prior_args + normalized_args_delta
                last_call_key = call_key

        # finalize function call arguments
        function_calls: List[FunctionCall] = []
        for call_key in function_call_order:
            call = function_calls_map[call_key]
            buf = arg_buffers.get(call_key, "")
            if buf:
                try:
                    import json

                    call.arguments = json.loads(buf)
                except Exception:
                    call.arguments = {}
            function_calls.append(call)

        return LLMResponse(
            text="".join(text_chunks).strip(),
            function_calls=function_calls,
        )

    @staticmethod
    def _normalize_stream_text_delta(accumulated_text: str, incoming_text: str) -> str:
        """Normalize provider text deltas that may be cumulative snapshots.

        Some providers emit `delta.text` as the full generated text-so-far instead of
        token increments. This keeps streaming UI stable and prevents duplicate output.
        """
        if not incoming_text:
            return ""
        if not accumulated_text:
            return incoming_text

        if incoming_text.startswith(accumulated_text):
            return incoming_text[len(accumulated_text) :]
        if accumulated_text.endswith(incoming_text):
            return ""

        overlap_max = min(len(accumulated_text), len(incoming_text))
        for size in range(overlap_max, 0, -1):
            if accumulated_text.endswith(incoming_text[:size]):
                return incoming_text[size:]
        return incoming_text

    def _build_generation_config(self) -> GenerationConfig:
        return GenerationConfig(
            system_prompt=self.system_prompt,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )

    def _log_llm_metrics(self, step: int, start_time: float, usage: Optional[Dict[str, int]] = None) -> None:
        """Log LLM request metrics (tokens, cost, duration)."""
        llm_duration = (time.time() - start_time) * 1000  # Convert to ms
        if usage and usage.get("total_tokens") is not None:
            estimated_tokens = int(usage.get("total_tokens") or 0)
        else:
            estimated_tokens = sum(
                self.history_manager._estimate_tokens(msg) for msg in self.history_manager.get_history()
            )
        estimated_cost = (estimated_tokens / 1_000_000) * self._COST_PER_MILLION_TOKENS
        self.observer.log_llm_request(
            model=self.config.model,
            tokens=estimated_tokens,
            cost=estimated_cost,
            duration_ms=llm_duration,
            step=step,
            agent_id=self.agent_id,
        )

    def _parse_response(self, response: LLMResponse) -> tuple[list, list[str]]:
        """Parse LLM response into function_calls and text_parts."""
        function_calls = response.function_calls or []
        text_parts = [response.text] if response.text else []

        if not function_calls and not text_parts:
            raise TransientError("Empty LLM response: no text or tool calls")

        return function_calls, text_parts

    def _check_loop_guard(
        self,
        function_calls: list,
        response_text: str,
        state: Dict[str, Any],
    ) -> Optional[str]:
        """Update loop-guard state. Return a stop reason if stuck."""
        tool_only = bool(function_calls) and not response_text

        if tool_only:
            state["tool_only_steps"] += 1
        else:
            state["tool_only_steps"] = 0

        if tool_only and len(function_calls) == 1:
            current_call = {
                "name": function_calls[0].name,
                "args": dict(function_calls[0].arguments) if function_calls[0].arguments else {},
            }
            if state["last_call"] == current_call:
                state["same_call_repeats"] += 1
            else:
                state["same_call_repeats"] = 0
            state["last_call"] = current_call
        else:
            state["same_call_repeats"] = 0
            state["last_call"] = None

        if state["tool_only_steps"] >= self._MAX_TOOL_ONLY_STEPS:
            return (
                f"Loop guard triggered: {state['tool_only_steps']} consecutive tool-only steps "
                "without model text. Aborting to prevent token waste."
            )

        if state["same_call_repeats"] > 0 and state["last_call"] is not None:
            tool_name = state["last_call"].get("name", "unknown")
            limit = self._MAX_REPEAT_READ_ONLY if tool_name in self._READ_ONLY_TOOLS else self._MAX_REPEAT_DEFAULT
            if state["same_call_repeats"] >= limit:
                return (
                    f"Loop guard triggered: repeated tool call '{tool_name}' "
                    f"{state['same_call_repeats']} time(s) without model text. "
                    "Aborting to prevent token waste."
                )

        return None

    def _requires_tool_approval(self, function_calls: list) -> bool:
        for fc in function_calls:
            if fc.name in self._WRITE_TOOLS:
                return True
        return False

    def has_pending_tool_calls(self) -> bool:
        return len(self._pending_tool_calls) > 0

    def set_auto_approve_tools(self, enabled: bool) -> None:
        self._auto_approve_tools = bool(enabled)

    def is_auto_approve_enabled(self) -> bool:
        return self._auto_approve_tools

    def set_approval_handler(self, handler: Optional[Callable]) -> None:
        """Set async approval handler: (function_calls) → (approved_calls, rejection_reason)."""
        self._approval_handler = handler

    def set_tool_event_handler(self, handler: Optional[Callable]) -> None:
        """Set async tool event handler: (event_type, tool_name, args, result?, success?)."""
        self._tool_event_handler = handler

    def set_interrupt_checker(self, checker: Optional[Callable]) -> None:
        """Set async interrupt checker: () → bool."""
        self._interrupt_checker = checker

    def list_pending_tool_calls(self) -> List[Dict[str, Any]]:
        pending = []
        for fc in self._pending_tool_calls:
            pending.append(
                {
                    "name": fc.name,
                    "args": dict(fc.arguments) if getattr(fc, "arguments", None) else {},
                }
            )
        return pending

    async def approve_pending_tool_calls(self) -> List[Dict[str, Any]]:
        calls = list(self._pending_tool_calls)
        self._pending_tool_calls = []
        if not calls:
            return []

        calls, policy_responses = self._apply_tool_call_policy(calls)
        executed_responses: List[FunctionResponse] = []
        if calls:
            executed_responses = await asyncio.gather(
                *[self._execute_tool(fc) for fc in calls],
                return_exceptions=False,
            )
        responses = [*policy_responses, *executed_responses]

        # Add function responses to history for continuity
        if responses:
            tool_message = Message(
                role="tool",
                parts=[MessagePart.from_function_response(fr) for fr in responses],
            )
            self.history_manager.add_message(tool_message)
            if self.session_manager:
                await self._auto_save()

        results = []
        for fr in responses:
            results.append(
                {
                    "name": fr.name,
                    "result": fr.response.get("result") if getattr(fr, "response", None) else "",
                }
            )
        return results

    def reject_pending_tool_calls(self) -> int:
        count = len(self._pending_tool_calls)
        self._pending_tool_calls = []
        return count

    def _missing_required_tool_args(self, func_name: str, func_args: Dict[str, Any]) -> List[str]:
        """Return required args that are absent/empty for the target tool."""
        if func_name not in self._tools:
            return []
        _, schema = self._tools[func_name]
        params = getattr(schema, "parameters", {}) or {}
        required = params.get("required", [])
        if not isinstance(required, list):
            return []

        missing: List[str] = []
        for key in required:
            if not isinstance(key, str):
                continue
            value = func_args.get(key, None)
            if value is None:
                missing.append(key)
                continue
            if isinstance(value, str) and not value.strip():
                missing.append(key)
        return missing

    def _apply_tool_call_policy(
        self, function_calls: List[FunctionCall]
    ) -> tuple[List[FunctionCall], List[FunctionResponse]]:
        """Apply execution-time policy filters to model tool calls."""
        has_job_search = any(fc.name == self._JOB_SEARCH_TOOL for fc in function_calls)
        has_job_detail = any(fc.name == self._JOB_DETAIL_TOOL for fc in function_calls)
        if not (has_job_search and has_job_detail):
            return function_calls, []

        filtered_calls: List[FunctionCall] = []
        rejected_responses: List[FunctionResponse] = []
        for fc in function_calls:
            if fc.name != self._JOB_DETAIL_TOOL:
                filtered_calls.append(fc)
                continue

            rejected = FunctionResponse(
                name=fc.name,
                response={"result": self._JOB_DETAIL_CONFLICT_REASON},
                call_id=fc.id,
            )
            rejected_responses.append(rejected)
            self.observer.log_error(
                error_type="tool_policy",
                message=self._JOB_DETAIL_CONFLICT_REASON,
                context={"tool": fc.name, "args": dict(fc.arguments) if fc.arguments else {}},
                agent_id=self.agent_id,
            )
            self.observer.log_tool_call(
                tool_name=fc.name,
                args=dict(fc.arguments) if fc.arguments else {},
                result=self._JOB_DETAIL_CONFLICT_REASON,
                duration_ms=0.0,
                success=False,
                cached=False,
                agent_id=self.agent_id,
            )
        return filtered_calls, rejected_responses

    async def _execute_tool(self, fc: FunctionCall) -> FunctionResponse:
        """Execute a single tool call, with caching and observability."""
        func_name = fc.name
        func_args = dict(fc.arguments) if fc.arguments else {}

        tool_start_time = time.time()
        success = True
        result_str = ""
        cached = False
        tool_error = None

        # Notify tool start
        if self._tool_event_handler:
            await self._tool_event_handler("tool_start", func_name, func_args, None, None)

        # Check cache first (only for cacheable tools)
        if should_cache_tool(func_name):
            cached_result = self.cache.get(func_name, func_args)
            if cached_result is not None:
                result_str = cached_result
                cached = True
                success = True

        # If not cached, execute the tool
        if not cached:
            if func_name in self._tools:
                func, _ = self._tools[func_name]
                missing_required = self._missing_required_tool_args(func_name, func_args)
                if missing_required:
                    success = False
                    result_str = (
                        f"Error: Invalid tool call for '{func_name}': "
                        f"missing required argument(s): {', '.join(missing_required)}"
                    )
                    tool_error = result_str
                else:
                    try:
                        # Execute the tool (await if async)
                        if asyncio.iscoroutinefunction(func):
                            result = await func(**func_args)
                        else:
                            result = func(**func_args)

                        # Convert ToolResult to string if needed
                        if hasattr(result, "to_message"):
                            result_str = result.to_message()
                            success = getattr(result, "success", True)
                            tool_error = getattr(result, "error", None)
                        else:
                            result_str = str(result)

                        # Cache only successful tool results
                        if success and should_cache_tool(func_name):
                            ttl = get_tool_ttl(func_name)
                            self.cache.set(func_name, func_args, result_str, ttl)

                    except Exception as e:
                        success = False
                        result_str = f"Error: {str(e)}"
                        tool_error = str(e)
                        self.observer.log_error(
                            error_type="tool_execution",
                            message=str(e),
                            context={"tool": func_name, "args": func_args},
                            agent_id=self.agent_id,
                        )
            else:
                success = False
                result_str = f"Error: Unknown tool '{func_name}'"
                self.observer.log_error(
                    error_type="unknown_tool",
                    message=f"Tool '{func_name}' not found",
                    context={"tool": func_name},
                    agent_id=self.agent_id,
                )

        # Log tool execution
        tool_duration = (time.time() - tool_start_time) * 1000
        if not success and tool_error:
            self.observer.log_error(
                error_type="tool_execution",
                message=str(tool_error),
                context={"tool": func_name, "args": func_args},
                agent_id=self.agent_id,
            )

        self.observer.log_tool_call(
            tool_name=func_name,
            args=func_args,
            result=result_str,
            duration_ms=tool_duration,
            success=success,
            cached=cached,
            agent_id=self.agent_id,
        )

        # Notify tool end
        if self._tool_event_handler:
            await self._tool_event_handler("tool_end", func_name, func_args, result_str, success)

        return FunctionResponse(
            name=func_name,
            response={"result": result_str},
            call_id=fc.id,
        )

    async def _auto_save(self):
        """Trigger auto-save."""
        if self.session_manager:
            try:
                # Get the agent instance (passed from parent)
                # This will be set by ResumeAgent or OrchestratorAgent
                if hasattr(self, "_parent_agent"):
                    self.current_session_id = self.session_manager.save_session(
                        agent=self._parent_agent,
                        session_id=self.current_session_id,
                    )
            except Exception as e:
                # Don't crash on auto-save failure
                if self.verbose:
                    print(f"Warning: Auto-save failed: {e}")

    def reset(self):
        """Reset conversation history."""
        self.history_manager.clear()
        self.current_session_id = None


# Backwards compatibility
GeminiAgent = LLMAgent


def load_raw_config(config_path: str = "config/config.local.yaml") -> dict:
    """Load raw configuration dictionary from YAML file.

    Priority order:
    1. config.local.yaml (user's local config with secrets)
    2. config.yaml (template/defaults)
    """
    from pathlib import Path

    import yaml

    repo_root = Path(__file__).resolve().parents[2]

    def _resolve(candidate: str) -> Path:
        path = Path(candidate)
        if path.exists():
            return path
        alt = repo_root / candidate
        if alt.exists():
            return alt
        return path

    def _load_yaml(path: Path) -> dict:
        if not path.exists():
            return {}
        with open(path) as f:
            data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                raise ValueError(f"Config file must be a mapping: {path}")
            return data

    def _deep_merge(base: dict, override: dict) -> dict:
        merged = dict(base)
        for key, value in override.items():
            base_value = merged.get(key)
            if isinstance(base_value, dict) and isinstance(value, dict):
                merged[key] = _deep_merge(base_value, value)
            else:
                merged[key] = value
        return merged

    target = _resolve(config_path)
    is_local_default = Path(config_path).name == "config.local.yaml"

    # Default behavior: load config.yaml first, then overlay config.local.yaml.
    if is_local_default:
        base_path = _resolve("config/config.yaml")
        local_path = target
        base = _load_yaml(base_path)
        local = _load_yaml(local_path)
        merged = _deep_merge(base, local)
        if not merged:
            raise FileNotFoundError(f"Config file not found: {config_path} (also missing fallback config/config.yaml)")
        return merged

    # Explicit non-local config path: load as-is.
    data = _load_yaml(target)
    if not data:
        raise FileNotFoundError(f"Config file not found: {config_path}")
    return data


def load_config(config_path: str = "config/config.local.yaml") -> LLMConfig:
    """Load LLM configuration from YAML file."""
    data = load_raw_config(config_path)

    config = LLMConfig(
        api_key=data.get("api_key", ""),
        provider=data.get("provider", "gemini"),
        model=data.get("model", "gemini-2.0-flash"),
        max_tokens=data.get("max_tokens", 4096),
        temperature=data.get("temperature", 0.7),
        api_base=data.get("api_base", ""),
        search_grounding=data.get("search_grounding", {}).get("enabled", False),
    )

    return config
