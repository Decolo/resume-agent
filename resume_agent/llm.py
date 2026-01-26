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

from .retry import retry_with_backoff, RetryConfig
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
        self._history.append(message)
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

        # Check if msg1 is model with function calls
        has_function_call = (
            msg1.role == "model" and
            msg1.parts is not None and
            any(part.function_call for part in msg1.parts)
        )

        # Check if msg2 is user with function responses
        has_function_response = (
            msg2.role == "user" and
            msg2.parts is not None and
            any(part.function_response for part in msg2.parts)
        )

        return has_function_call and has_function_response

    def _fix_broken_pairs(self):
        """
        Fix broken function call/response pairs after pruning.

        If history starts with an orphaned function response (user message with
        function_response but no preceding function_call), remove it.
        """
        if not self._history:
            return

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

    def _estimate_tokens(self, message: types.Content) -> int:
        """
        Estimate token count for a message.

        Uses rough heuristic: 1 token ≈ 4 characters
        """
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

    def __init__(self, config: LLMConfig, system_prompt: str = ""):
        self.config = config
        self.system_prompt = system_prompt
        self._resolve_api_key()

        # Initialize the client
        self.client = genai.Client(api_key=self.config.api_key)

        # Tools registry: name -> (function, schema)
        self._tools: Dict[str, tuple] = {}

        # History manager with automatic pruning
        self.history_manager = HistoryManager(max_messages=50, max_tokens=100000)

        # Observability for logging and metrics
        self.observer = AgentObserver()

        # Tool result caching
        self.cache = ToolCache()

    def _resolve_api_key(self):
        """Resolve API key from environment if needed."""
        if self.config.api_key.startswith("${") and self.config.api_key.endswith("}"):
            env_var = self.config.api_key[2:-1]
            self.config.api_key = os.environ.get(env_var, "")
        if not self.config.api_key:
            # Try common env vars
            self.config.api_key = os.environ.get("GEMINI_API_KEY", "")
        if not self.config.api_key:
            raise ValueError("GEMINI_API_KEY not set")

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
        if not self._tools:
            return None
        
        declarations = [schema for _, (_, schema) in self._tools.items()]
        return [types.Tool(function_declarations=declarations)]

    async def run(self, user_input: str, max_steps: int = 20) -> str:
        """Run the agent with user input, handling tool calls automatically."""
        # Add user message to history
        self.history_manager.add_message(types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_input)],
        ))
        
        step = 0
        while step < max_steps:
            step += 1

            # Log step start
            self.observer.log_step_start(step, user_input if step == 1 else None)

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

            response = await retry_with_backoff(
                make_llm_request,
                retry_config
            )

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
                step=step
            )
            
            # Check for function calls
            candidate = response.candidates[0]
            parts = candidate.content.parts
            
            function_calls = []
            text_parts = []
            
            for part in parts:
                if part.function_call:
                    function_calls.append(part.function_call)
                elif part.text:
                    text_parts.append(part.text)
            
            # Add model response to history
            self.history_manager.add_message(candidate.content)
            
            if function_calls:
                # Execute function calls in parallel
                async def execute_single_tool(fc):
                    """Execute a single tool call and return the response."""
                    func_name = fc.name
                    func_args = dict(fc.args) if fc.args else {}

                    tool_start_time = time.time()
                    success = True
                    result_str = ""
                    cached = False

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
                                if hasattr(result, 'to_message'):
                                    result_str = result.to_message()
                                else:
                                    result_str = str(result)

                                # Cache the result if tool is cacheable
                                if should_cache_tool(func_name):
                                    ttl = get_tool_ttl(func_name)
                                    self.cache.set(func_name, func_args, result_str, ttl)

                            except Exception as e:
                                success = False
                                result_str = f"Error: {str(e)}"
                                self.observer.log_error(
                                    error_type="tool_execution",
                                    message=str(e),
                                    context={"tool": func_name, "args": func_args}
                                )
                        else:
                            success = False
                            result_str = f"Error: Unknown tool '{func_name}'"
                            self.observer.log_error(
                                error_type="unknown_tool",
                                message=f"Tool '{func_name}' not found",
                                context={"tool": func_name}
                            )

                    # Log tool execution
                    tool_duration = (time.time() - tool_start_time) * 1000
                    self.observer.log_tool_call(
                        tool_name=func_name,
                        args=func_args,
                        result=result_str,
                        duration_ms=tool_duration,
                        success=success,
                        cached=cached
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
                
                # Add function responses to history
                self.history_manager.add_message(types.Content(
                    role="user",
                    parts=function_responses,
                ))

                # Log step end
                step_duration = (time.time() - start_time) * 1000
                self.observer.log_step_end(step, step_duration)
            else:
                # No function calls - return the text response
                step_duration = (time.time() - start_time) * 1000
                self.observer.log_step_end(step, step_duration)

                final_text = "".join(text_parts)

                # Print session summary
                self.observer.print_session_summary()

                # Print cache statistics
                self.cache.print_stats()

                return final_text

        return f"Max steps ({max_steps}) reached."

    def reset(self):
        """Reset conversation history."""
        self.history_manager.clear()


def load_config(config_path: str = "config/config.yaml") -> LLMConfig:
    """Load LLM configuration from YAML file."""
    import yaml
    from pathlib import Path

    path = Path(config_path)
    if not path.exists():
        path = Path(__file__).parent.parent / config_path

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    config = LLMConfig(
        api_key=data.get("api_key", ""),
        model=data.get("model", "gemini-2.0-flash"),
        max_tokens=data.get("max_tokens", 4096),
        temperature=data.get("temperature", 0.7),
    )

    # Add extra fields for OpenAI compatibility
    config.api_type = data.get("api_type", "gemini")
    config.api_base = data.get("api_base", "")

    return config
