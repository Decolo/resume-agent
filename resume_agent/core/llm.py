"""LLM client and history management."""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

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
from .retry import RetryConfig, TransientError, is_transient_error, retry_with_backoff

if TYPE_CHECKING:
    from .wire import Wire


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
    # Backward-compatible fallback when a tool is registered without capabilities.
    _WRITE_TOOLS = {"file_write", "resume_write", "file_rename"}

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
        self._debug_tool_args = self.verbose or os.getenv("RESUME_AGENT_DEBUG_TOOL_ARGS", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

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
        self._tool_policies: Dict[str, Dict[str, Any]] = {}

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
        # Auto-approve tool calls that require approval
        self._auto_approve_tools = False
        # Session-scoped action-level approvals (tool action keys, e.g. "file_write").
        self._auto_approve_actions: set[str] = set()

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
        *,
        requires_approval: Optional[bool] = None,
        mutation_signature_fields: Optional[List[str]] = None,
    ):
        """Register a tool that the agent can use."""
        schema = ToolSchema(name=name, description=description, parameters=parameters)
        self._tools[name] = (func, schema)
        self._tool_policies[name] = {
            "requires_approval": requires_approval,
            "mutation_signature_fields": tuple(mutation_signature_fields)
            if mutation_signature_fields is not None
            else None,
        }

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
        *,
        wire: Wire,
    ) -> str:
        """Run the agent with user input using the wire-mode event loop."""
        return await self._run_wire(
            user_input,
            max_steps=max_steps,
            stream=stream,
            on_stream_delta=on_stream_delta,
            wire=wire,
        )

    # --- Wire-mode agent loop ---

    async def _run_wire(
        self,
        user_input: str,
        *,
        max_steps: int = 20,
        stream: bool = False,
        on_stream_delta: Optional[Callable[[StreamDelta], None]] = None,
        wire: Wire,
    ) -> str:
        """Agent loop with Wire event bus — approval happens inline.

        Control-flow contract (high level):
        1) LLM responds with text and/or tool calls.
        2) Optional approval gate runs inside the same loop iteration.
        3) Approved tool calls execute, emit wire events, then write tool results to history.
        4) Loop continues until model returns no tool calls, a fatal condition triggers,
           or max_steps is reached.
        """
        from .wire.approval import Approval, ApprovalState
        from .wire.types import (
            StepBegin,
            ToolCallEvent,
            ToolResultEvent,
            TurnBegin,
            TurnEnd,
        )

        self.history_manager.add_message(Message.user(user_input))
        self.history_manager._ensure_valid_sequence()

        def _persist_approval_state() -> None:
            self._auto_approve_actions = set(approval_state.auto_approve_actions)

        approval_state = ApprovalState(
            yolo=self._auto_approve_tools,
            auto_approve_actions=self._auto_approve_actions,
            on_change=_persist_approval_state,
        )
        approval = Approval(state=approval_state)
        pipe_task: Optional[asyncio.Task] = None

        wire.soul_side.send(TurnBegin(user_input=user_input))

        response_text = ""
        try:
            for step in range(1, max_steps + 1):
                if self._interrupt_checker and await self._interrupt_checker():
                    raise asyncio.CancelledError("Run interrupted")

                self.observer.log_step_start(step, user_input if step == 1 else None, agent_id=self.agent_id)
                start_time = time.time()
                wire.soul_side.send(StepBegin(n=step))

                # 1. Call LLM
                try:
                    response = await self._call_llm_with_resilience(
                        stream=stream,
                        on_stream_delta=on_stream_delta,
                        wire=wire,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self.observer.log_error(
                        error_type="llm_request",
                        message=str(e),
                        context={"model": self.config.model, "step": step},
                        agent_id=self.agent_id,
                    )
                    response_text = f"Error: LLM request failed: {e}"
                    break

                # 2. Log LLM metrics
                self._log_llm_metrics(step, start_time, response.usage)
                self._log_raw_response_debug(step, response)

                # 3. Parse response
                function_calls, text_parts = self._parse_response(response)
                function_calls = self._repair_function_call_args_from_raw_response(function_calls, response.raw)
                response_text = " ".join(text_parts).strip()

                # 4. Log response summary
                tool_calls_dump = []
                if function_calls:
                    for fc in function_calls:
                        tool_calls_dump.append({"name": fc.name, "args": dict(fc.arguments) if fc.arguments else {}})
                self.observer.log_llm_response(
                    step=step,
                    text=response_text or "(no text)",
                    tool_calls=tool_calls_dump,
                    agent_id=self.agent_id,
                )
                if function_calls:
                    self._log_empty_write_args_debug(function_calls, step, response.raw)

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

                # 6. If no tool calls -> done
                if not function_calls:
                    if self.session_manager:
                        await self._auto_save()
                    step_duration = (time.time() - start_time) * 1000
                    self.observer.log_step_end(step, step_duration, agent_id=self.agent_id)
                    break

                # 7. Inline approval (replaces pause-and-return)
                if self._requires_tool_approval(function_calls) and not approval.is_yolo():
                    approved_calls: Optional[List[FunctionCall]] = function_calls
                    rejection_reason = ""

                    if self._approval_handler is not None:
                        approved_calls, rejection_reason = await self._approval_handler(function_calls)
                    else:
                        if not self._wire_has_ui_subscribers(wire):
                            # No UI consumer means an approval request can never be answered.
                            # Fail fast here instead of hanging the turn indefinitely.
                            response_text = (
                                "Error: Tool call(s) require approval, but no Wire UI consumer or "
                                "approval handler is available."
                            )
                            self.observer.log_error(
                                error_type="approval_unavailable",
                                message=response_text,
                                context={"step": step},
                                agent_id=self.agent_id,
                            )
                            step_duration = (time.time() - start_time) * 1000
                            self.observer.log_step_end(step, step_duration, agent_id=self.agent_id)
                            break

                        # Start pipe task if not already running
                        if pipe_task is None or pipe_task.done():
                            # Background bridge: Approval.fetch_request() -> Wire ApprovalRequest.
                            # The main loop awaits `approval.request(...)` below, while this task
                            # forwards the request and resolves it from UI/user input.
                            pipe_task = asyncio.create_task(self._pipe_approval_to_wire(approval, wire))

                        approved_calls = []
                        rejected_calls: List[FunctionCall] = []
                        rejection_reason = "user declined approval"
                        for fc in function_calls:
                            if not self._tool_requires_approval(fc.name):
                                approved_calls.append(fc)
                                continue

                            action, description = await self._build_approval_for_call(fc)
                            approved = await approval.request(action, [fc], description)
                            if approved:
                                approved_calls.append(fc)
                            else:
                                rejected_calls.append(fc)

                        if rejected_calls:
                            rejection_message = self._build_rejection_tool_message(rejected_calls, rejection_reason)
                            self.history_manager.add_message(rejection_message)

                    if not approved_calls:
                        step_duration = (time.time() - start_time) * 1000
                        self.observer.log_step_end(step, step_duration, agent_id=self.agent_id)
                        continue

                    function_calls = approved_calls

                # 8. Emit ToolCallEvents + execute tools
                for fc in function_calls:
                    wire.soul_side.send(
                        ToolCallEvent(
                            name=fc.name,
                            arguments=dict(fc.arguments) if fc.arguments else {},
                            call_id=fc.id,
                        )
                    )

                # Execute calls from one model turn concurrently.
                # This assumes calls in the same batch are independent; if a provider emits
                # dependency-ordered calls in one response, that ordering is not preserved here.
                executed_responses = await asyncio.gather(
                    *[self._execute_tool(fc) for fc in function_calls],
                    return_exceptions=False,
                )
                function_responses = list(executed_responses)

                # 9. Emit ToolResultEvents
                for fc, fr in zip(function_calls, executed_responses):
                    result_str = fr.response.get("result", "") if fr.response else ""
                    wire.soul_side.send(
                        ToolResultEvent(
                            name=fc.name,
                            result=result_str,
                            call_id=fc.id,
                            success="Error:" not in result_str,
                        )
                    )

                # 10. Update history + auto-save
                tool_message = Message(
                    role="tool",
                    parts=[MessagePart.from_function_response(fr) for fr in function_responses],
                )
                self.history_manager.add_message(tool_message)
                if self.session_manager:
                    await self._auto_save()

                # Some tool-call errors are considered unrecoverable for this turn (for example:
                # missing required arguments). We still persist the tool message above so the
                # model/user can inspect the failure in history/session logs.
                fatal_tool_error = self._fatal_tool_error_message(function_calls, executed_responses)
                if fatal_tool_error:
                    response_text = fatal_tool_error
                    step_duration = (time.time() - start_time) * 1000
                    self.observer.log_step_end(step, step_duration, agent_id=self.agent_id)
                    break

                step_duration = (time.time() - start_time) * 1000
                self.observer.log_step_end(step, step_duration, agent_id=self.agent_id)
            else:
                response_text = f"Max steps ({max_steps}) reached."

        finally:
            if pipe_task is not None and not pipe_task.done():
                pipe_task.cancel()
                try:
                    await pipe_task
                except asyncio.CancelledError:
                    pass

        wire.soul_side.send(TurnEnd(final_text=response_text))

        if self.verbose:
            self.observer.print_session_summary()
            self.cache.print_stats()

        return response_text

    async def _pipe_approval_to_wire(self, approval: Any, wire: Wire) -> None:
        """Background task: fetch approval requests and pipe them to the Wire."""
        from .wire.types import ApprovalRequest

        try:
            while True:
                req = await approval.fetch_request()
                wire_req = ApprovalRequest(
                    id=req.id,
                    action=req.action,
                    tool_calls=req.tool_calls,
                    description=req.description,
                )
                wire.soul_side.send(wire_req)
                resp = await wire_req.wait()
                approval.resolve_request(req.id, resp)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def _build_approval_for_call(self, function_call: FunctionCall) -> tuple[str, str]:
        """Build action + description for a single function call approval."""
        args = dict(function_call.arguments) if function_call.arguments else {}
        default_action = function_call.name or "tool_call"

        # Baseline fallback description.
        arg_pairs: List[str] = []
        for k, v in args.items():
            if isinstance(v, str):
                preview = v if len(v) <= 80 else f"{v[:80]}…"
                arg_pairs.append(f"{k}={preview!r}")
            else:
                arg_pairs.append(f"{k}={v!r}")
        arg_preview = ", ".join(arg_pairs)
        fallback_description = f"{function_call.name}({arg_preview})"
        fallback_action = default_action

        # Prefer tool-provided action/description when available.
        tool_entry = self._tools.get(function_call.name)
        if tool_entry:
            func, _schema = tool_entry
            tool_instance = getattr(func, "__self__", None)
            if tool_instance is not None:
                request_builder = getattr(tool_instance, "build_approval_request", None)
                if callable(request_builder):
                    try:
                        spec = request_builder(**args)
                        if asyncio.iscoroutine(spec):
                            spec = await spec
                        action = getattr(spec, "action", None)
                        description = getattr(spec, "description", None)
                        if isinstance(action, str) and action.strip():
                            fallback_action = action.strip()
                        if isinstance(description, str) and description.strip():
                            return fallback_action, description
                    except Exception as e:
                        self._log_tool_arg_debug(
                            "approval_request_build_failed",
                            "Tool-provided approval request builder failed.",
                            {"tool": function_call.name, "error": str(e)},
                        )

        preview = await self._build_tool_approval_preview(function_call.name, args)
        if preview:
            fallback_description = f"{fallback_description}\n\n{preview}"
        return fallback_action, fallback_description

    async def _build_tool_approval_preview(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Ask the tool instance for approval preview text, if it provides a hook."""
        tool_entry = self._tools.get(tool_name)
        if not tool_entry:
            return ""

        func, _schema = tool_entry
        tool_instance = getattr(func, "__self__", None)
        if tool_instance is None:
            return ""

        preview_builder = getattr(tool_instance, "build_approval_context", None)
        if not callable(preview_builder):
            return ""

        try:
            preview = preview_builder(**args)
            if asyncio.iscoroutine(preview):
                preview = await preview
            return preview if isinstance(preview, str) else ""
        except Exception as e:
            # Approval preview is best-effort and must never block tool execution.
            self._log_tool_arg_debug(
                "approval_preview_build_failed",
                "Tool-provided approval preview builder failed.",
                {"tool": tool_name, "error": str(e)},
            )
            return ""

    @staticmethod
    def _build_rejection_tool_message(function_calls: List[FunctionCall], reason: str) -> Message:
        """Build a synthetic tool message for rejected tool calls."""
        return Message(
            role="tool",
            parts=[
                MessagePart.from_function_response(
                    FunctionResponse(
                        name=fc.name,
                        response={"result": f"Rejected: {reason}"},
                        call_id=fc.id,
                    )
                )
                for fc in function_calls
            ],
        )

    # --- Extracted helper methods ---

    async def _call_llm(self) -> LLMResponse:
        """Call LLM with retry logic."""

        async def make_request():
            messages = list(self.history_manager.get_history())
            response = await self.provider.generate(
                messages=messages,
                tools=self._get_tools(),
                config=self._build_generation_config(),
            )
            self._raise_if_retryable_malformed_function_call(response)
            # Retry empty responses in the provider-call layer so the main loop
            # only handles actionable LLM outputs.
            if not response.text and not response.function_calls:
                raise TransientError("Empty LLM response: no text or tool calls")
            return response

        return await retry_with_backoff(make_request, self._retry_config)

    async def _call_llm_with_resilience(
        self,
        *,
        stream: bool,
        on_stream_delta: Optional[Callable[[StreamDelta], None]] = None,
        wire: Optional[Wire] = None,
    ) -> LLMResponse:
        """Call LLM with transport resilience.

        In streaming mode, transient transport failures are downgraded to
        non-streaming generation (which already has retry-with-backoff).
        """
        if not stream:
            return await self._call_llm()

        try:
            return await self._call_llm_stream(on_stream_delta=on_stream_delta, wire=wire)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if not is_transient_error(e):
                raise

            self.observer.log_error(
                error_type="llm_stream_fallback",
                message=str(e),
                context={"model": self.config.model, "fallback": "non_stream"},
                agent_id=self.agent_id,
            )
            return await self._call_llm()

    async def _call_llm_stream(
        self,
        on_stream_delta: Optional[Callable[[StreamDelta], None]] = None,
        wire: Optional[Wire] = None,
    ) -> LLMResponse:
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
                    # Emit TextDelta to wire if active
                    if wire is not None:
                        from .wire.types import TextDelta

                        wire.soul_side.send(TextDelta(text=normalized_text))

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
                    function_calls_map[call_key] = FunctionCall(
                        name=call.name,
                        arguments=dict(call.arguments) if call.arguments else {},
                        id=call_id,
                        thought_signature=call.thought_signature,
                    )
                    function_call_order.append(call_key)
                else:
                    existing_call = function_calls_map[call_key]
                    if not existing_call.name and call.name:
                        existing_call.name = call.name
                    if not existing_call.id:
                        existing_call.id = call_id
                    if not existing_call.arguments and call.arguments:
                        existing_call.arguments = dict(call.arguments)
                    if existing_call.thought_signature is None and call.thought_signature is not None:
                        existing_call.thought_signature = call.thought_signature

                arg_buffers.setdefault(call_key, "")
                last_call_key = call_key
                self._log_tool_arg_debug(
                    "stream_function_call_start",
                    "Observed function_call_start in stream.",
                    {
                        "call_key": call_key,
                        "call_id": call_id,
                        "function_name": call.name,
                        "start_args_summary": self._summarize_argument_shapes(
                            dict(call.arguments) if call.arguments else {}
                        ),
                    },
                )

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

                # Merge argument chunks conservatively: support cumulative
                # snapshots, partial dict snapshots, and plain incremental text.
                prior_args = arg_buffers.get(call_key, "")
                merged_args = self._merge_stream_argument_buffer(prior_args, delta.function_call_delta)
                arg_buffers[call_key] = merged_args
                self._log_tool_arg_debug(
                    "stream_function_call_delta",
                    "Merged function_call_delta into argument buffer.",
                    {
                        "call_key": call_key,
                        "delta_len": len(delta.function_call_delta),
                        "delta_sha": self._fingerprint_text(delta.function_call_delta),
                        "buffer_len_before": len(prior_args),
                        "buffer_len_after": len(merged_args),
                        "buffer_sha_after": self._fingerprint_text(merged_args),
                    },
                )
                last_call_key = call_key

        # finalize function call arguments
        function_calls: List[FunctionCall] = []
        for call_key in function_call_order:
            call = function_calls_map[call_key]
            buf = arg_buffers.get(call_key, "")
            if buf:
                parsed_args = self._parse_tool_argument_buffer(buf)
                if parsed_args is not None:
                    call.arguments = parsed_args
                    self._log_tool_arg_debug(
                        "stream_function_call_args_parsed",
                        "Parsed argument buffer into structured tool args.",
                        {
                            "call_key": call_key,
                            "function_name": call.name,
                            "buffer_len": len(buf),
                            "buffer_sha": self._fingerprint_text(buf),
                            "args_summary": self._summarize_argument_shapes(parsed_args),
                        },
                    )
                else:
                    self._log_tool_arg_debug(
                        "stream_function_call_args_parse_failed",
                        "Failed to parse argument buffer; keeping existing call.arguments.",
                        {
                            "call_key": call_key,
                            "function_name": call.name,
                            "buffer_len": len(buf),
                            "buffer_sha": self._fingerprint_text(buf),
                            "existing_args_summary": self._summarize_argument_shapes(call.arguments or {}),
                        },
                    )
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

    @staticmethod
    def _merge_stream_argument_buffer(accumulated_text: str, incoming_text: str) -> str:
        """Merge streamed argument chunks while preserving parseability."""
        if not incoming_text:
            return accumulated_text
        if not accumulated_text:
            return incoming_text

        # Cumulative snapshots from some providers.
        if incoming_text.startswith(accumulated_text):
            return incoming_text
        # Repeated stale snapshots.
        if accumulated_text.startswith(incoming_text):
            return accumulated_text

        # If both sides parse as dict and incoming has at least the same keys,
        # treat incoming as a fresh snapshot replacement.
        prior_dict = LLMAgent._parse_tool_argument_buffer(accumulated_text)
        incoming_dict = LLMAgent._parse_tool_argument_buffer(incoming_text)
        if isinstance(prior_dict, dict) and isinstance(incoming_dict, dict):
            if set(incoming_dict.keys()) >= set(prior_dict.keys()):
                return incoming_text

        # Best-effort overlap merge for true incremental chunks.
        overlap_max = min(len(accumulated_text), len(incoming_text))
        for size in range(overlap_max, 0, -1):
            if accumulated_text.endswith(incoming_text[:size]):
                return accumulated_text + incoming_text[size:]
        return accumulated_text + incoming_text

    @staticmethod
    def _parse_tool_argument_buffer(raw: str) -> Optional[Dict[str, Any]]:
        """Parse streamed tool arguments into a dictionary when possible."""
        if not raw:
            return {}

        try:
            import json

            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        # Recover from duplicated/concatenated JSON snapshots by scanning for
        # the "best" parseable dict object inside the buffer.
        try:
            import json

            decoder = json.JSONDecoder()
            best: Optional[Dict[str, Any]] = None
            best_score = -1
            for idx, ch in enumerate(raw):
                if ch != "{":
                    continue
                try:
                    candidate, _end = decoder.raw_decode(raw[idx:])
                except Exception:
                    continue
                if not isinstance(candidate, dict):
                    continue
                score = len(candidate)
                if "path" in candidate:
                    score += 100
                if "content" in candidate:
                    score += 200
                if score > best_score:
                    best = candidate
                    best_score = score
            if best is not None:
                return best
        except Exception:
            pass

        # Some OpenAI-compatible providers may emit Python-style dict strings
        # (`{'path': 'x'}`) in stream deltas.
        try:
            import ast

            parsed = ast.literal_eval(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        return None

    @staticmethod
    def _summarize_argument_shapes(args: Dict[str, Any]) -> Dict[str, str]:
        """Return a non-sensitive summary of argument value shapes."""
        summary: Dict[str, str] = {}
        for key, value in args.items():
            if isinstance(value, str):
                summary[key] = f"str(len={len(value)})"
            elif isinstance(value, dict):
                summary[key] = f"dict(len={len(value)})"
            elif isinstance(value, list):
                summary[key] = f"list(len={len(value)})"
            elif value is None:
                summary[key] = "none"
            else:
                summary[key] = type(value).__name__
        return summary

    @staticmethod
    def _fingerprint_text(text: str) -> str:
        """Stable short fingerprint for debug correlation without full payload."""
        if not text:
            return "0"
        return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[:12]

    def _log_tool_arg_debug(self, debug_type: str, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Emit debug events for tool-argument stream reconstruction."""
        if not self._debug_tool_args:
            return
        self.observer.log_debug(
            debug_type=debug_type,
            message=message,
            context=context or {},
            agent_id=self.agent_id,
        )

    def _log_raw_response_debug(self, step: int, response: LLMResponse) -> None:
        """Emit a structured raw-response snapshot before response parsing."""
        if not self._debug_tool_args:
            return

        raw = response.raw
        normalized_text = response.text or ""
        normalized_calls = response.function_calls or []

        if raw is None:
            self._log_tool_arg_debug(
                "llm_raw_response_missing",
                "Provider response.raw is empty before parse.",
                {
                    "step": step,
                    "provider": self.config.provider,
                    "model": self.config.model,
                    "normalized_text_len": len(normalized_text),
                    "normalized_tool_calls": len(normalized_calls),
                },
            )
            return

        raw_summary = self._summarize_raw_response(raw)
        preview, preview_total_len, preview_truncated = self._build_raw_response_preview(raw)
        self._log_tool_arg_debug(
            "llm_raw_response_summary",
            "Captured provider raw response summary before parse.",
            {
                "step": step,
                "provider": self.config.provider,
                "model": self.config.model,
                "raw_type": type(raw).__name__,
                "normalized_text_len": len(normalized_text),
                "normalized_tool_calls": len(normalized_calls),
                "raw_summary": raw_summary,
                "raw_preview_len": preview_total_len,
                "raw_preview_truncated": preview_truncated,
                "raw_preview": preview,
            },
        )

    @staticmethod
    def _summarize_raw_response(raw_response: Any) -> Dict[str, Any]:
        """Summarize provider raw response shape in a provider-agnostic way."""
        summary: Dict[str, Any] = {"raw_type": type(raw_response).__name__}

        # Gemini-like shape
        if hasattr(raw_response, "candidates"):
            candidates = getattr(raw_response, "candidates", None) or []
            summary["shape"] = "gemini_like"
            summary["candidates_count"] = len(candidates)
            if candidates:
                candidate0 = candidates[0]
                summary["candidate0_finish_reason"] = str(getattr(candidate0, "finish_reason", None))
                content = getattr(candidate0, "content", None)
                parts = getattr(content, "parts", None) or []
                summary["candidate0_parts_count"] = len(parts)
                parts_summary: List[Dict[str, Any]] = []
                for idx, part in enumerate(parts[:6]):
                    entry: Dict[str, Any] = {"index": idx}
                    text = getattr(part, "text", None)
                    if isinstance(text, str):
                        entry["text_len"] = len(text)
                    thought = getattr(part, "thought", None)
                    if thought is not None:
                        entry["thought"] = bool(thought)
                    function_call = getattr(part, "function_call", None)
                    if function_call is not None:
                        entry["function_name"] = getattr(function_call, "name", None)
                        args = getattr(function_call, "args", None)
                        entry["function_args_type"] = type(args).__name__ if args is not None else "none"
                        try:
                            if isinstance(args, dict):
                                entry["function_arg_keys"] = sorted(args.keys())
                            elif args is not None:
                                entry["function_args_len"] = len(str(args))
                        except Exception:
                            pass
                    parts_summary.append(entry)
                if parts_summary:
                    summary["candidate0_parts"] = parts_summary
            return summary

        # OpenAI-compatible shape
        if hasattr(raw_response, "choices"):
            choices = getattr(raw_response, "choices", None) or []
            summary["shape"] = "openai_like"
            summary["choices_count"] = len(choices)
            if choices:
                choice0 = choices[0]
                summary["choice0_finish_reason"] = str(getattr(choice0, "finish_reason", None))
                message = getattr(choice0, "message", None)
                if message is not None:
                    content = getattr(message, "content", None)
                    summary["choice0_content_type"] = type(content).__name__ if content is not None else "none"
                    if isinstance(content, str):
                        summary["choice0_content_len"] = len(content)
                    elif isinstance(content, list):
                        summary["choice0_content_items"] = len(content)
                    tool_calls = getattr(message, "tool_calls", None) or []
                    summary["choice0_tool_calls_count"] = len(tool_calls)
                    if tool_calls:
                        names: List[str] = []
                        for call in tool_calls[:6]:
                            fn = getattr(call, "function", None)
                            names.append(str(getattr(fn, "name", "")))
                        summary["choice0_tool_call_names"] = names
            return summary

        return summary

    @staticmethod
    def _build_raw_response_preview(raw_response: Any) -> tuple[str, int, bool]:
        """Serialize raw response into a truncated preview for observability."""
        preview_limit = 3000
        try:
            raw_limit = os.getenv("RESUME_AGENT_DEBUG_RAW_PREVIEW_CHARS", "").strip()
            if raw_limit:
                preview_limit = int(raw_limit)
        except Exception:
            preview_limit = 3000
        preview_limit = max(256, min(preview_limit, 20000))

        raw_text = ""
        try:
            if hasattr(raw_response, "model_dump_json"):
                raw_text = str(raw_response.model_dump_json(exclude_none=True))
            elif hasattr(raw_response, "model_dump"):
                import json

                raw_text = json.dumps(raw_response.model_dump(exclude_none=True), ensure_ascii=True)
            else:
                raw_text = repr(raw_response)
        except Exception:
            raw_text = repr(raw_response)

        raw_len = len(raw_text)
        truncated = raw_len > preview_limit
        if truncated:
            return raw_text[:preview_limit], raw_len, True
        return raw_text, raw_len, False

    def _build_generation_config(self) -> GenerationConfig:
        return GenerationConfig(
            system_prompt=self.system_prompt,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )

    def _raise_if_retryable_malformed_function_call(self, response: LLMResponse) -> None:
        """Raise transient error for provider-level malformed tool-call replies."""
        if not self._is_retryable_malformed_function_call_response(response):
            return

        raw_summary = self._summarize_raw_response(response.raw)
        self.observer.log_error(
            error_type="llm_malformed_function_call",
            message="Provider returned MALFORMED_FUNCTION_CALL without callable payload. Retrying.",
            context={
                "provider": self.config.provider,
                "model": self.config.model,
                "raw_summary": raw_summary,
            },
            agent_id=self.agent_id,
        )
        raise TransientError("Provider returned MALFORMED_FUNCTION_CALL without callable payload")

    @staticmethod
    def _is_retryable_malformed_function_call_response(response: LLMResponse) -> bool:
        """Detect malformed function-call responses that should be retried."""
        if response.text or response.function_calls:
            return False

        raw = response.raw
        if raw is None or not hasattr(raw, "candidates"):
            return False

        candidates = getattr(raw, "candidates", None) or []
        if not candidates:
            return False

        candidate0 = candidates[0]
        finish_reason = str(getattr(candidate0, "finish_reason", "") or "").upper()
        if "MALFORMED_FUNCTION_CALL" not in finish_reason:
            return False

        content = getattr(candidate0, "content", None)
        parts = getattr(content, "parts", None) or []
        return len(parts) == 0

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

    def _repair_function_call_args_from_raw_response(
        self,
        function_calls: List[FunctionCall],
        raw_response: Optional[Any],
    ) -> List[FunctionCall]:
        """Best-effort repair for parsed args using provider raw response."""
        if not function_calls or raw_response is None:
            return function_calls

        raw_calls = self._extract_raw_tool_calls(raw_response)
        if not raw_calls:
            return function_calls

        repaired: List[FunctionCall] = []
        for fc in function_calls:
            args = dict(fc.arguments) if fc.arguments else {}

            raw_entry = self._match_raw_tool_call(fc, raw_calls)
            if not raw_entry:
                repaired.append(fc)
                continue

            raw_args = raw_entry.get("arguments")
            parsed = self._best_effort_parse_raw_tool_args(raw_args)
            required_keys = self._required_tool_keys(fc.name)
            if parsed and self._should_prefer_parsed_tool_args(fc.name, args, parsed, required_keys):
                fc.arguments = parsed
                self._log_tool_arg_debug(
                    "llm_repaired_tool_args_from_raw",
                    "Recovered/expanded tool args from raw provider response.",
                    {
                        "tool": fc.name,
                        "call_id": fc.id,
                        "old_keys": sorted(args.keys()),
                        "new_keys": sorted(parsed.keys()),
                        "old_content_len": len(args.get("content", ""))
                        if isinstance(args.get("content"), str)
                        else None,
                        "new_content_len": (
                            len(parsed.get("content", "")) if isinstance(parsed.get("content"), str) else None
                        ),
                        "raw_type": type(raw_args).__name__,
                        "raw_len": len(raw_args) if isinstance(raw_args, str) else None,
                    },
                )
            repaired.append(fc)
        return repaired

    def _required_tool_keys(self, tool_name: str) -> set[str]:
        if tool_name not in self._tools:
            return set()
        _func, schema = self._tools[tool_name]
        params = getattr(schema, "parameters", {}) or {}
        required = params.get("required", [])
        if not isinstance(required, list):
            return set()
        return {k for k in required if isinstance(k, str)}

    @staticmethod
    def _should_prefer_parsed_tool_args(
        tool_name: str,
        current_args: Dict[str, Any],
        parsed_args: Dict[str, Any],
        required_keys: set[str],
    ) -> bool:
        if not parsed_args:
            return False
        if not current_args:
            return True

        current_keys = set(current_args.keys())
        parsed_keys = set(parsed_args.keys())

        # Prefer candidate when it fills required keys missing from current args.
        if required_keys and not required_keys.issubset(current_keys) and required_keys.issubset(parsed_keys):
            return True

        # Prefer candidate when it contains strictly more keys.
        if parsed_keys > current_keys:
            return True

        # Prefer longer payload for common heavy fields.
        for heavy_key in ("content", "command", "text", "body", "code", "data"):
            cur_val = current_args.get(heavy_key)
            new_val = parsed_args.get(heavy_key)
            if isinstance(cur_val, str) and isinstance(new_val, str):
                if len(new_val) > len(cur_val) + 32:
                    return True

        # Prefer non-truncated-looking content for write tools.
        if tool_name in {"file_write", "resume_write"}:
            cur_content = current_args.get("content")
            new_content = parsed_args.get("content")
            if isinstance(cur_content, str) and isinstance(new_content, str):
                if cur_content.endswith("\\") and len(new_content) >= len(cur_content):
                    return True

        return False

    @staticmethod
    def _extract_raw_tool_calls(raw_response: Any) -> List[Dict[str, Any]]:
        """Extract raw provider tool calls in OpenAI-compatible shape."""
        choices = getattr(raw_response, "choices", None) or []
        if not choices:
            return []
        message = getattr(choices[0], "message", None)
        if message is None:
            return []
        tool_calls = getattr(message, "tool_calls", None) or []
        extracted: List[Dict[str, Any]] = []
        for idx, call in enumerate(tool_calls):
            function = getattr(call, "function", None)
            extracted.append(
                {
                    "index": idx,
                    "id": getattr(call, "id", None),
                    "name": getattr(function, "name", "") if function else "",
                    "arguments": getattr(function, "arguments", None) if function else None,
                }
            )
        return extracted

    @staticmethod
    def _match_raw_tool_call(fc: FunctionCall, raw_calls: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if fc.id:
            for rc in raw_calls:
                if rc.get("id") == fc.id:
                    return rc
        name_matches = [rc for rc in raw_calls if rc.get("name") == fc.name]
        if len(name_matches) == 1:
            return name_matches[0]
        return name_matches[0] if name_matches else None

    def _best_effort_parse_raw_tool_args(self, raw_args: Any) -> Dict[str, Any]:
        if raw_args is None:
            return {}
        if isinstance(raw_args, dict):
            return raw_args
        if not isinstance(raw_args, str):
            return {}

        # Reuse stream parser first.
        parsed = self._parse_tool_argument_buffer(raw_args)
        if parsed:
            return parsed

        # Reuse provider parser when available (OpenAI-compatible provider has
        # richer malformed-JSON recovery tailored to real-world tool-call args).
        parser = getattr(self.provider, "_safe_parse_args", None)
        if callable(parser):
            try:
                parsed2 = parser(raw_args)
                if isinstance(parsed2, dict) and parsed2:
                    return parsed2
            except Exception:
                pass

        return {}

    def _tool_requires_approval(self, tool_name: str) -> bool:
        policy = self._tool_policies.get(tool_name, {})
        requires_approval = policy.get("requires_approval")
        if requires_approval is not None:
            return bool(requires_approval)
        return tool_name in self._WRITE_TOOLS

    def _requires_tool_approval(self, function_calls: list) -> bool:
        for fc in function_calls:
            if self._tool_requires_approval(fc.name):
                return True
        return False

    def _log_empty_write_args_debug(
        self,
        function_calls: List[FunctionCall],
        step: int,
        raw_response: Optional[Any] = None,
    ) -> None:
        """Emit targeted debug signal when write tools arrive with empty args."""
        raw_summaries = self._extract_raw_tool_call_argument_summaries(raw_response)
        for fc in function_calls:
            if not self._tool_requires_approval(fc.name):
                continue
            args = dict(fc.arguments) if fc.arguments else {}
            if args:
                continue
            raw_summary = self._select_raw_summary_for_function_call(fc, raw_summaries)
            self._log_tool_arg_debug(
                "llm_response_empty_write_args",
                "LLM returned write tool call with empty args.",
                {"step": step, "tool": fc.name, "call_id": fc.id, "raw_args_summary": raw_summary},
            )

    @staticmethod
    def _extract_raw_tool_call_argument_summaries(raw_response: Optional[Any]) -> List[Dict[str, Any]]:
        """Extract non-sensitive summaries of raw provider tool_call arguments."""
        if raw_response is None:
            return []
        choices = getattr(raw_response, "choices", None) or []
        if not choices:
            return []
        choice0 = choices[0]
        message = getattr(choice0, "message", None)
        if message is None:
            return []
        tool_calls = getattr(message, "tool_calls", None) or []

        summaries: List[Dict[str, Any]] = []
        for idx, call in enumerate(tool_calls):
            fn = getattr(call, "function", None)
            name = getattr(fn, "name", "") if fn else ""
            raw_args = getattr(fn, "arguments", None) if fn else None
            raw_type = type(raw_args).__name__ if raw_args is not None else "none"
            raw_text = ""
            if raw_args is not None:
                try:
                    if isinstance(raw_args, str):
                        raw_text = raw_args
                    else:
                        import json

                        raw_text = json.dumps(raw_args, ensure_ascii=False)
                except Exception:
                    raw_text = str(raw_args)
            summaries.append(
                {
                    "index": idx,
                    "id": getattr(call, "id", None),
                    "name": name,
                    "raw_type": raw_type,
                    "raw_len": len(raw_text),
                    "raw_sha": LLMAgent._fingerprint_text(raw_text),
                    "raw_present": bool(raw_text.strip()) if isinstance(raw_text, str) else bool(raw_text),
                }
            )
        return summaries

    @staticmethod
    def _select_raw_summary_for_function_call(
        fc: FunctionCall,
        raw_summaries: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Pick the most relevant raw-summary entry for a function call."""
        if not raw_summaries:
            return {}
        if fc.id:
            for s in raw_summaries:
                if s.get("id") == fc.id:
                    return s
        matches = [s for s in raw_summaries if s.get("name") == fc.name]
        if len(matches) == 1:
            return matches[0]
        return matches[0] if matches else raw_summaries[0]

    @staticmethod
    def _is_invalid_tool_call_missing_args_error(result: str) -> bool:
        if not isinstance(result, str):
            return False
        return result.startswith("Error: Invalid tool call for ") and "missing required argument(s):" in result

    def _fatal_tool_error_message(
        self,
        function_calls: List[FunctionCall],
        responses: List[FunctionResponse],
    ) -> Optional[str]:
        """Return a user-facing fatal message for unrecoverable tool-call errors."""
        for fc, fr in zip(function_calls, responses):
            result = fr.response.get("result", "") if fr and fr.response else ""
            if self._is_invalid_tool_call_missing_args_error(result):
                self.observer.log_error(
                    error_type="invalid_tool_call",
                    message=result,
                    context={"tool": fc.name, "call_id": fc.id},
                    agent_id=self.agent_id,
                )
                return (
                    f"{result}\n" "Turn aborted to prevent repeated approval/tool loops. " "Please retry the command."
                )
        return None

    @staticmethod
    def _wire_has_ui_subscribers(wire: Wire) -> bool:
        """Best-effort check: a Wire has at least one UI subscriber."""
        queue = getattr(wire, "_queue", None)
        subscribers = getattr(queue, "_queues", None)
        return bool(subscribers)

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

    @staticmethod
    def _has_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        return True

    def _infer_single_file_from_recent_file_list(self) -> Optional[str]:
        """Infer a likely file path from recent file_list tool results."""
        history = list(self.history_manager.get_history())
        for msg in reversed(history):
            if msg.role != "tool" or not msg.parts:
                continue
            for part in msg.parts:
                fr = part.function_response
                if fr is None or fr.name != "file_list":
                    continue
                response = fr.response or {}
                raw = response.get("result", "")
                if not isinstance(raw, str) or not raw:
                    continue

                files: List[str] = []
                for line in raw.splitlines():
                    cols = line.split("\t", 2)
                    if len(cols) != 3:
                        continue
                    file_type, _size, path = cols
                    if file_type.strip() == "file" and path.strip():
                        files.append(path.strip())

                if not files:
                    continue
                if len(files) == 1:
                    return files[0]

                resume_candidates = [p for p in files if "resume" in p.lower()]
                if len(resume_candidates) == 1:
                    return resume_candidates[0]
        return None

    def _normalize_tool_args(self, func_name: str, func_args: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize common argument aliases and infer obvious missing file path."""
        if func_name not in self._tools:
            return func_args

        _, schema = self._tools[func_name]
        params = getattr(schema, "parameters", {}) or {}
        properties = params.get("properties", {}) or {}

        normalized = dict(func_args)

        # Common aliases emitted by models.
        alias_map: Dict[str, tuple[str, ...]] = {
            "path": ("file_path", "filename", "resume_path"),
            "resume_path": ("path", "file_path"),
            "content": ("text",),
        }

        for canonical, aliases in alias_map.items():
            if canonical not in properties:
                continue
            if self._has_value(normalized.get(canonical)):
                continue
            for alias in aliases:
                if self._has_value(normalized.get(alias)):
                    normalized[canonical] = normalized[alias]
                    break

        # If path is still missing, infer from recent file_list when unambiguous.
        if "path" in properties and not self._has_value(normalized.get("path")):
            inferred = self._infer_single_file_from_recent_file_list()
            if inferred:
                normalized["path"] = inferred

        return normalized

    async def _execute_tool(self, fc: FunctionCall) -> FunctionResponse:
        """Execute a single tool call, with caching and observability."""
        func_name = fc.name
        func_args = self._normalize_tool_args(func_name, dict(fc.arguments) if fc.arguments else {})

        tool_start_time = time.time()
        success = True
        result_str = ""
        cached = False
        tool_error = None
        tool_data: Dict[str, Any] = {}

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
                    self._log_tool_arg_debug(
                        "tool_call_missing_required_args",
                        "Tool execution blocked due to missing required args.",
                        {
                            "tool": func_name,
                            "missing_required": missing_required,
                            "provided_args_summary": self._summarize_argument_shapes(func_args),
                            "call_id": fc.id,
                        },
                    )
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
                            raw_data = getattr(result, "data", None)
                            if isinstance(raw_data, dict):
                                tool_data = raw_data
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
            response={"result": result_str, "success": success, "data": tool_data},
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
