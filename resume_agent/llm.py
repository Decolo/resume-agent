"""LLM Client - Uses Google GenAI SDK for Gemini with function calling."""

from __future__ import annotations

import json
import os
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

from google import genai
from google.genai import types

from .retry import retry_with_backoff, RetryConfig, TransientError
from .observability import AgentObserver
from .cache import ToolCache, should_cache_tool, get_tool_ttl


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
        self._history: List[types.Content] = []

    def add_message(self, message: types.Content):
        """Add a message and prune if needed."""
        if message is None:
            return
        self._history.append(message)
        # Remove any accidental None entries in history
        if any(m is None for m in self._history):
            self._history = [m for m in self._history if m is not None]
        self._ensure_valid_sequence()
        self._prune_if_needed()

    def get_history(self) -> List[types.Content]:
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
            self._history = self._history[-self.max_messages:]
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
        - history[index] has role="model" with function_call parts
        - history[index+1] has role="user" with function_response parts
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

        If history starts with an orphaned function response (user message with
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
        if (first_msg.role == "user" and
            first_msg.parts is not None and
            any(part.function_response for part in first_msg.parts)):
            # This is an orphaned response, remove it
            self._history.pop(0)

        # Check if last message is an orphaned function call
        if self._history:
            last_msg = self._history[-1]
            if (last_msg.role == "model" and
                last_msg.parts is not None and
                any(part.function_call for part in last_msg.parts)):
                # This is an orphaned call, remove it
                self._history.pop()

    def _has_function_call(self, msg: types.Content) -> bool:
        return (
            msg is not None and
            msg.role == "model" and
            msg.parts is not None and
            any(part.function_call for part in msg.parts)
        )

    def _has_function_response(self, msg: types.Content) -> bool:
        return (
            msg is not None and
            msg.role == "user" and
            msg.parts is not None and
            any(part.function_response for part in msg.parts)
        )

    def _ensure_valid_sequence(self):
        """Ensure history ordering is valid for Gemini function calling."""
        if not self._history:
            return

        # Remove None entries
        self._history = [m for m in self._history if m is not None]
        if not self._history:
            return

        cleaned: List[types.Content] = []
        for msg in self._history:
            # Drop orphaned function responses
            if self._has_function_response(msg):
                if not cleaned:
                    continue
                if not self._has_function_call(cleaned[-1]):
                    continue
            # Drop model function calls that do not follow a user turn
            if self._has_function_call(msg):
                if not cleaned:
                    continue
                if cleaned[-1].role != "user":
                    continue
            cleaned.append(msg)

        # Drop model function calls not followed by a user function response
        final: List[types.Content] = []
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

    def _estimate_tokens(self, message: types.Content) -> int:
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
                # Estimate function call size
                total_chars += len(part.function_call.name) * 2
                if part.function_call.args:
                    total_chars += len(str(dict(part.function_call.args)))
            elif part.function_response:
                # Estimate function response size
                total_chars += len(part.function_response.name) * 2
                if part.function_response.response:
                    total_chars += len(str(dict(part.function_response.response)))

        return total_chars // 4  # Rough estimate: 4 chars per token


@dataclass
class Message:
    """A message in the conversation."""
    role: str  # "user", "model", "tool"
    content: str
    tool_calls: Optional[List[dict]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


@dataclass
class LLMConfig:
    """Configuration for LLM client."""
    api_key: str
    model: str = "gemini-2.0-flash"
    max_tokens: int = 4096
    temperature: float = 0.7
    api_base: str = ""  # Custom API endpoint (proxy)
    search_grounding: bool = False


@dataclass
class ToolCall:
    """A tool call from the model."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    """Response from LLM."""
    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"


class GeminiAgent:
    """Agent using Google GenAI SDK with function calling."""

    def __init__(self, config: LLMConfig, system_prompt: str = "", agent_id: Optional[str] = None, session_manager: Optional[Any] = None):
        self.config = config
        self.system_prompt = system_prompt
        self.agent_id = agent_id
        self._resolve_api_key()

        # Initialize the client
        self.client = genai.Client(api_key=self.config.api_key)

        # Tools registry: name -> (function, schema)
        self._tools: Dict[str, tuple] = {}

        # History manager with automatic pruning
        self.history_manager = HistoryManager(max_messages=50, max_tokens=100000)

        # Observability for logging and metrics
        self.observer = AgentObserver(agent_id=agent_id)

        # Tool result caching
        self.cache = ToolCache()

        # Session management
        self.session_manager = session_manager
        self.auto_save_enabled = False
        self.current_session_id: Optional[str] = None

    def _resolve_api_key(self):
        """Resolve API key with priority: env var > config file.

        Priority order:
        1. GEMINI_API_KEY environment variable
        2. api_key from config file
        3. Raise error if neither is set
        """
        # First, try environment variable (highest priority)
        env_key = os.environ.get("GEMINI_API_KEY", "")
        if env_key:
            self.config.api_key = env_key
            return

        # Second, check if config has a key (not a placeholder)
        if self.config.api_key and not self.config.api_key.startswith("${"):
            return

        # Third, try to resolve ${VAR_NAME} placeholder in config
        if self.config.api_key.startswith("${") and self.config.api_key.endswith("}"):
            env_var = self.config.api_key[2:-1]
            resolved = os.environ.get(env_var, "")
            if resolved:
                self.config.api_key = resolved
                return

        # No valid API key found
        raise ValueError(
            "GEMINI_API_KEY not set. Please either:\n"
            "  1. Set GEMINI_API_KEY environment variable, or\n"
            "  2. Add 'api_key: your_key' to config/config.local.yaml"
        )

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        func: Callable,
    ):
        """Register a tool that the agent can use."""
        # Convert OpenAI-style parameters to Gemini format
        properties = {}
        required = parameters.get("required", [])
        
        for prop_name, prop_def in parameters.get("properties", {}).items():
            prop_type = prop_def.get("type", "string").upper()
            if prop_type == "STRING":
                prop_type = "STRING"
            elif prop_type == "INTEGER":
                prop_type = "INTEGER"
            elif prop_type == "NUMBER":
                prop_type = "NUMBER"
            elif prop_type == "BOOLEAN":
                prop_type = "BOOLEAN"
            else:
                prop_type = "STRING"
            
            properties[prop_name] = types.Schema(
                type=prop_type,
                description=prop_def.get("description", ""),
            )
        
        schema = types.FunctionDeclaration(
            name=name,
            description=description,
            parameters=types.Schema(
                type="OBJECT",
                properties=properties,
                required=required,
            ),
        )
        
        self._tools[name] = (func, schema)

    def _get_tools(self) -> Optional[List[types.Tool]]:
        """Get tools in Gemini format."""
        tools: List[types.Tool] = []

        if self._tools:
            declarations = [schema for _, (_, schema) in self._tools.items()]
            tools.append(types.Tool(function_declarations=declarations))

        if self.config.search_grounding:
            tools.append(types.Tool(google_search=types.GoogleSearch()))

        return tools or None

    async def run(self, user_input: str, max_steps: int = 20) -> str:
        """Run the agent with user input, handling tool calls automatically."""
        # Add user message to history
        self.history_manager.add_message(types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_input)],
        ))

        # Ensure history ordering is valid before calling the model
        self.history_manager._ensure_valid_sequence()

        last_tool_call: Optional[Dict[str, Any]] = None
        repeated_tool_calls = 0
        last_tool_result: Optional[str] = None

        step = 0
        while step < max_steps:
            step += 1

            # Log step start
            self.observer.log_step_start(
                step,
                user_input if step == 1 else None,
                agent_id=self.agent_id,
            )

            # Generate response with retry logic
            import time
            start_time = time.time()

            async def make_llm_request():
                return self.client.models.generate_content(
                    model=self.config.model,
                    contents=self.history_manager.get_history(),
                    config=types.GenerateContentConfig(
                        system_instruction=self.system_prompt if self.system_prompt else None,
                        tools=self._get_tools(),
                        max_output_tokens=self.config.max_tokens,
                        temperature=self.config.temperature,
                    ),
                )

            # Retry configuration for LLM calls
            retry_config = RetryConfig(
                max_attempts=3,
                base_delay=1.0,
                max_delay=60.0,
                exponential_base=2.0,
                jitter_factor=0.2
            )

            try:
                response = await retry_with_backoff(
                    make_llm_request,
                    retry_config
                )
            except Exception as e:
                self.observer.log_error(
                    error_type="llm_request",
                    message=str(e),
                    context={"model": self.config.model, "step": step},
                    agent_id=self.agent_id,
                )
                return f"Error: LLM request failed: {e}"

            # Log LLM request (rough token estimate and cost)
            llm_duration = (time.time() - start_time) * 1000  # Convert to ms
            estimated_tokens = sum(self.history_manager._estimate_tokens(msg)
                                   for msg in self.history_manager.get_history())
            # Gemini 2.5 Flash pricing: ~$0.08 per 1M input tokens
            estimated_cost = (estimated_tokens / 1_000_000) * 0.08
            self.observer.log_llm_request(
                model=self.config.model,
                tokens=estimated_tokens,
                cost=estimated_cost,
                duration_ms=llm_duration,
                step=step,
                agent_id=self.agent_id,
            )
            
            # Check for function calls
            # Validate response structure early
            if not response.candidates:
                raise TransientError("Empty LLM response: no candidates")

            candidate = response.candidates[0]
            parts = []
            if candidate.content and candidate.content.parts:
                parts = candidate.content.parts
            
            function_calls = []
            text_parts = []
            
            for part in parts:
                if part.function_call:
                    function_calls.append(part.function_call)
                elif part.text:
                    text_parts.append(part.text)

            if not parts or (not function_calls and not text_parts):
                # Treat empty responses as transient to trigger retry upstream
                raise TransientError("Empty LLM response: no text or tool calls")

            # Log a brief response summary for debugging
            response_text = " ".join(text_parts).strip()
            tool_calls_dump = []
            if function_calls:
                for fc in function_calls:
                    tool_calls_dump.append({
                        "name": fc.name,
                        "args": dict(fc.args) if fc.args else {},
                    })
            self.observer.log_llm_response(
                step=step,
                text=response_text or "(no text)",
                tool_calls=tool_calls_dump,
                agent_id=self.agent_id,
            )

            # Add model response to history
            self.history_manager.add_message(candidate.content)
            
            if function_calls:
                # Detect repeated identical tool calls with no text output
                if not response_text and len(function_calls) == 1:
                    current_call = {"name": function_calls[0].name, "args": dict(function_calls[0].args) if function_calls[0].args else {}}
                    if last_tool_call == current_call:
                        repeated_tool_calls += 1
                    else:
                        repeated_tool_calls = 0
                    last_tool_call = current_call
                else:
                    repeated_tool_calls = 0
                    last_tool_call = None

                # Execute function calls in parallel
                async def execute_single_tool(fc):
                    """Execute a single tool call and return the response."""
                    func_name = fc.name
                    func_args = dict(fc.args) if fc.args else {}

                    tool_start_time = time.time()
                    success = True
                    result_str = ""
                    cached = False
                    tool_error = None

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

                    return types.Part.from_function_response(
                        name=func_name,
                        response={"result": result_str},
                    )

                # Execute all tools in parallel
                function_responses = await asyncio.gather(
                    *[execute_single_tool(fc) for fc in function_calls],
                    return_exceptions=False
                )

                # Capture last tool result for fallback
                if len(function_calls) == 1:
                    fr = getattr(function_responses[0], "function_response", None)
                    if fr and getattr(fr, "response", None):
                        last_tool_result = fr.response.get("result")

                # Add function responses to history
                self.history_manager.add_message(types.Content(
                    role="user",
                    parts=function_responses,
                ))

                # Auto-save after tool execution
                if self.auto_save_enabled and self.session_manager:
                    await self._auto_save()

                # Log step end
                step_duration = (time.time() - start_time) * 1000
                self.observer.log_step_end(step, step_duration, agent_id=self.agent_id)

                # If the model is stuck repeating the same tool call, return the last tool result
                if repeated_tool_calls >= 1 and last_tool_result:
                    return last_tool_result
            else:
                # No function calls - return the text response
                step_duration = (time.time() - start_time) * 1000
                self.observer.log_step_end(step, step_duration, agent_id=self.agent_id)

                final_text = "".join(text_parts)

                # Print session summary
                self.observer.print_session_summary()

                # Print cache statistics
                self.cache.print_stats()

                return final_text

        return f"Max steps ({max_steps}) reached."

    async def _auto_save(self):
        """Trigger auto-save."""
        if self.session_manager:
            try:
                # Get the agent instance (passed from parent)
                # This will be set by ResumeAgent or OrchestratorAgent
                if hasattr(self, '_parent_agent'):
                    self.current_session_id = self.session_manager.save_session(
                        agent=self._parent_agent,
                        session_id=self.current_session_id,
                        auto_save=True
                    )
            except Exception as e:
                # Don't crash on auto-save failure
                print(f"Warning: Auto-save failed: {e}")

    def reset(self):
        """Reset conversation history."""
        self.history_manager.clear()
        self.current_session_id = None


def load_raw_config(config_path: str = "config/config.local.yaml") -> dict:
    """Load raw configuration dictionary from YAML file.

    Priority order:
    1. config.local.yaml (user's local config with secrets)
    2. config.yaml (template/defaults)
    """
    import yaml
    from pathlib import Path

    path = Path(config_path)
    if not path.exists():
        path = Path(__file__).parent.parent / config_path

    # If config.local.yaml doesn't exist, try config.yaml as fallback
    if not path.exists():
        fallback_path = path.with_name("config.yaml")
        if fallback_path.exists():
            path = fallback_path
        else:
            fallback_path = Path(__file__).parent.parent / "config" / "config.yaml"
            if fallback_path.exists():
                path = fallback_path

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path) as f:
        return yaml.safe_load(f)


def load_config(config_path: str = "config/config.local.yaml") -> LLMConfig:
    """Load LLM configuration from YAML file."""
    data = load_raw_config(config_path)

    config = LLMConfig(
        api_key=data.get("api_key", ""),
        model=data.get("model", "gemini-2.0-flash"),
        max_tokens=data.get("max_tokens", 4096),
        temperature=data.get("temperature", 0.7),
        api_base=data.get("api_base", ""),
        search_grounding=data.get("search_grounding", {}).get("enabled", False),
    )

    return config
