"""OpenAI-compatible LLM Client - Works with OpenAI, Claude, Gemini proxies."""

from __future__ import annotations

import json
import os
import asyncio
import httpx
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .retry import retry_with_backoff, RetryConfig
from .observability import AgentObserver
from .cache import ToolCache, should_cache_tool, get_tool_ttl


@dataclass
class OpenAIConfig:
    """Configuration for OpenAI-compatible API."""
    api_key: str
    api_base: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    max_tokens: int = 4096
    temperature: float = 0.7


class OpenAIAgent:
    """Agent using OpenAI-compatible API (works with OpenAI, Claude proxies, etc.)."""

    def __init__(self, config: OpenAIConfig, system_prompt: str = ""):
        self.config = config
        self.system_prompt = system_prompt
        self._resolve_api_key()

        # HTTP client
        self.client = httpx.AsyncClient(timeout=60.0)

        # Tools registry
        self._tools: Dict[str, tuple] = {}
        self._tool_schemas: List[Dict] = []

        # Observability
        self.observer = AgentObserver()
        self.cache = ToolCache()

        # History
        self.history: List[Dict] = []
        if system_prompt:
            self.history.append({"role": "system", "content": system_prompt})

    def _resolve_api_key(self):
        """Resolve API key from environment if needed."""
        if self.config.api_key.startswith("${") and self.config.api_key.endswith("}"):
            env_var = self.config.api_key[2:-1]
            self.config.api_key = os.getenv(env_var, "")

        if self.config.api_base.startswith("${") and self.config.api_base.endswith("}"):
            env_var = self.config.api_base[2:-1]
            self.config.api_base = os.getenv(env_var, "https://api.openai.com/v1")

        if self.config.model.startswith("${") and self.config.model.endswith("}"):
            env_var = self.config.model[2:-1]
            self.config.model = os.getenv(env_var, "gpt-4o-mini")

    def register_tool(self, name: str, description: str, parameters: Dict[str, Any], func: callable):
        """Register a tool with its function and schema."""
        self._tools[name] = (func, {"description": description, "parameters": parameters})

        # Convert to OpenAI tool format
        tool_def = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters
            }
        }
        self._tool_schemas.append(tool_def)

    async def run(self, user_input: str, max_steps: int = 50) -> str:
        """Run the agent loop."""
        # Add user message
        self.history.append({"role": "user", "content": user_input})

        step = 0
        while step < max_steps:
            step += 1
            self.observer.log_step_start(step)

            # Make LLM request with retry
            retry_config = RetryConfig(max_attempts=3, base_delay=1.0)

            async def make_request():
                return await self._make_api_call()

            response = await retry_with_backoff(make_request, retry_config)

            # Check if we have tool calls
            message = response["choices"][0]["message"]

            if message.get("tool_calls"):
                # Execute tools
                self.history.append(message)

                for tool_call in message["tool_calls"]:
                    tool_name = tool_call["function"]["name"]
                    tool_args = json.loads(tool_call["function"]["arguments"])

                    # Execute tool
                    result = await self._execute_tool(tool_name, tool_args)

                    # Add tool response to history
                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": tool_name,
                        "content": result
                    })

                self.observer.log_step_end(step, success=True)
                continue

            # No tool calls - return response
            content = message.get("content", "")
            self.history.append(message)
            self.observer.log_step_end(step, success=True)

            # Print session summary
            self.observer.print_session_summary()
            self.cache.print_stats()

            return content

        return "Max steps reached"

    async def _make_api_call(self) -> Dict:
        """Make API call to OpenAI-compatible endpoint."""
        url = f"{self.config.api_base}/chat/completions"

        payload = {
            "model": self.config.model,
            "messages": self.history,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }

        if self._tool_schemas:
            payload["tools"] = self._tool_schemas

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}"
        }

        response = await self.client.post(url, json=payload, headers=headers)
        response.raise_for_status()

        return response.json()

    async def _execute_tool(self, tool_name: str, tool_args: Dict) -> str:
        """Execute a tool and return result."""
        if tool_name not in self._tools:
            return f"Error: Tool {tool_name} not found"

        func, schema = self._tools[tool_name]

        # Check cache
        if should_cache_tool(tool_name):
            cached = self.cache.get(tool_name, tool_args)
            if cached:
                self.observer.log_tool_call(tool_name, tool_args, cached[:200], 0, True, True)
                return cached

        # Execute
        start_time = asyncio.get_event_loop().time()

        if asyncio.iscoroutinefunction(func):
            result = await func(**tool_args)
        else:
            result = func(**tool_args)

        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000

        # Get result string
        if hasattr(result, 'to_message'):
            result_str = result.to_message()
        else:
            result_str = str(result)

        # Cache if applicable
        if should_cache_tool(tool_name):
            ttl = get_tool_ttl(tool_name)
            self.cache.set(tool_name, tool_args, result_str, ttl)

        self.observer.log_tool_call(tool_name, tool_args, result_str[:200], duration_ms, True, False)

        return result_str

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
