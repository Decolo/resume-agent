"""OpenAI-compatible provider implementation."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from .types import (
    FunctionCall,
    GenerationConfig,
    LLMResponse,
    Message,
    StreamDelta,
    ToolSchema,
)


class OpenAICompatibleProvider:
    """Provider for OpenAI-compatible chat APIs."""

    def __init__(
        self,
        api_key: str,
        model: str,
        api_base: str = "",
    ) -> None:
        self.model = model
        self.api_base = api_base or ""
        self.client = AsyncOpenAI(api_key=api_key, base_url=api_base or None)
        self._forced_temperature: Optional[float] = None

    async def generate(
        self,
        messages: List[Message],
        tools: Optional[List[ToolSchema]],
        config: GenerationConfig,
    ) -> LLMResponse:
        openai_messages = self._to_openai_messages(messages, config.system_prompt)
        openai_tools = self._to_openai_tools(tools)
        kwargs = self._build_chat_kwargs(
            messages=openai_messages,
            tools=openai_tools,
            config=config,
            stream=False,
        )
        completion = await self._create_with_temperature_retry(kwargs)

        return self._from_openai_completion(completion)

    async def generate_stream(
        self,
        messages: List[Message],
        tools: Optional[List[ToolSchema]],
        config: GenerationConfig,
    ):
        openai_messages = self._to_openai_messages(messages, config.system_prompt)
        openai_tools = self._to_openai_tools(tools)
        kwargs = self._build_chat_kwargs(
            messages=openai_messages,
            tools=openai_tools,
            config=config,
            stream=True,
        )
        stream = await self._create_with_temperature_retry(kwargs)
        call_ids_by_index: Dict[int, str] = {}

        async for chunk in stream:
            deltas = self._iter_stream_deltas(chunk, call_ids_by_index)
            for delta in deltas:
                yield delta

    def _build_chat_kwargs(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        config: GenerationConfig,
        stream: bool,
    ) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }
        if config.max_tokens and config.max_tokens > 0:
            kwargs["max_tokens"] = config.max_tokens
        normalized_temperature = self._normalize_temperature(config.temperature)
        if normalized_temperature is not None:
            kwargs["temperature"] = normalized_temperature
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        extra_body = self._build_extra_body()
        if extra_body:
            kwargs["extra_body"] = extra_body
        return kwargs

    def _normalize_temperature(self, temperature: Optional[float]) -> Optional[float]:
        if self._forced_temperature is not None:
            return self._forced_temperature
        if temperature is None:
            return None
        return temperature

    def _build_extra_body(self) -> Optional[Dict[str, Any]]:
        api_base_lower = self.api_base.lower()
        model_lower = (self.model or "").lower()

        # Moonshot Kimi K2/K2.5: disable thinking mode for stable tool-calling
        # compatibility in OpenAI-style multi-turn function-call loops.
        if "moonshot.cn" in api_base_lower and model_lower.startswith("kimi-k2"):
            return {"thinking": {"type": "disabled"}}

        return None

    async def _create_with_temperature_retry(self, kwargs: Dict[str, Any]):
        try:
            return await self.client.chat.completions.create(**kwargs)
        except Exception as error:
            allowed = self._extract_allowed_temperature(error)
            current = kwargs.get("temperature")
            if allowed is None or current == allowed:
                raise

            retry_kwargs = dict(kwargs)
            retry_kwargs["temperature"] = allowed
            self._forced_temperature = allowed
            return await self.client.chat.completions.create(**retry_kwargs)

    def _extract_allowed_temperature(self, error: Exception) -> Optional[float]:
        message = str(error).lower()
        if "invalid temperature" not in message:
            return None

        # Example: "invalid temperature: only 0.6 is allowed for this model"
        match = re.search(r"only\s+([0-9]+(?:\.[0-9]+)?)\s+is allowed", message)
        if not match:
            return None
        try:
            return float(match.group(1))
        except Exception:
            return None

    def _to_openai_messages(self, messages: List[Message], system_prompt: str) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})

        pending_ids: Dict[str, List[str]] = {}

        for msg in messages:
            if msg.role == "tool":
                for part in msg.parts:
                    if not part.function_response:
                        continue
                    call_id = part.function_response.call_id
                    if not call_id:
                        name = part.function_response.name
                        if pending_ids.get(name):
                            call_id = pending_ids[name].pop(0)
                        else:
                            call_id = f"tool_{uuid.uuid4().hex}"
                    content = self._tool_response_content(part.function_response.response)
                    result.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": content,
                        }
                    )
                continue

            role = "assistant" if msg.role == "assistant" else "user"
            text_parts = [p.text for p in msg.parts if p.text]
            content = "\n".join(text_parts) if text_parts else ""

            tool_calls = []
            for part in msg.parts:
                if not part.function_call:
                    continue
                call_id = part.function_call.id or f"tool_{uuid.uuid4().hex}"
                part.function_call.id = call_id
                pending_ids.setdefault(part.function_call.name, []).append(call_id)
                tool_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": part.function_call.name,
                            "arguments": json.dumps(part.function_call.arguments or {}),
                        },
                    }
                )

            message: Dict[str, Any] = {"role": role, "content": content}
            if tool_calls:
                message["tool_calls"] = tool_calls
            result.append(message)

        return result

    def _to_openai_tools(self, tools: Optional[List[ToolSchema]]) -> Optional[List[Dict[str, Any]]]:
        if not tools:
            return None
        converted = []
        for tool in tools:
            converted.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )
        return converted

    def _from_openai_completion(self, completion) -> LLMResponse:
        if not completion.choices:
            raise RuntimeError("Empty LLM response: no choices")

        choice = completion.choices[0]
        message = choice.message
        text = self._normalize_message_content(getattr(message, "content", ""))
        function_calls: List[FunctionCall] = []

        for call in getattr(message, "tool_calls", None) or []:
            function = getattr(call, "function", None)
            if function is None:
                continue
            args = self._safe_parse_args(getattr(function, "arguments", None))
            function_calls.append(
                FunctionCall(
                    name=getattr(function, "name", "") or "",
                    arguments=args,
                    id=getattr(call, "id", None),
                )
            )

        usage_data = getattr(completion, "usage", None)
        usage = None
        if usage_data:
            usage = {
                "prompt_tokens": int(getattr(usage_data, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage_data, "completion_tokens", 0) or 0),
                "total_tokens": int(getattr(usage_data, "total_tokens", 0) or 0),
            }

        return LLMResponse(
            text=text,
            function_calls=function_calls,
            usage=usage,
            raw=completion,
        )

    def _iter_stream_deltas(
        self,
        chunk: Any,
        call_ids_by_index: Dict[int, str],
    ) -> List[StreamDelta]:
        deltas: List[StreamDelta] = []
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            return deltas

        choice = choices[0]
        delta = getattr(choice, "delta", None)
        if delta is None:
            return deltas

        content = self._normalize_message_content(getattr(delta, "content", None))
        if content:
            deltas.append(StreamDelta(text=content))

        for tool_call in getattr(delta, "tool_calls", None) or []:
            call_index = getattr(tool_call, "index", None)
            raw_id = getattr(tool_call, "id", None)
            if isinstance(call_index, int) and raw_id:
                call_ids_by_index[call_index] = raw_id
            call_id = raw_id
            if not call_id and isinstance(call_index, int):
                call_id = call_ids_by_index.get(call_index)

            function = getattr(tool_call, "function", None)
            function_name = getattr(function, "name", None) if function else None
            args_delta = getattr(function, "arguments", None) if function else None

            if function_name:
                deltas.append(
                    StreamDelta(
                        function_call_start=FunctionCall(
                            name=function_name,
                            arguments={},
                            id=call_id,
                        ),
                        function_call_id=call_id,
                        function_call_index=call_index if isinstance(call_index, int) else None,
                    )
                )

            if args_delta:
                deltas.append(
                    StreamDelta(
                        function_call_delta=str(args_delta),
                        function_call_id=call_id,
                        function_call_index=call_index if isinstance(call_index, int) else None,
                    )
                )

        finish_reason = getattr(choice, "finish_reason", None)
        if finish_reason:
            deltas.append(
                StreamDelta(
                    function_call_end=finish_reason == "tool_calls",
                    finish_reason=finish_reason,
                )
            )
        return deltas

    def _tool_response_content(self, response: Any) -> str:
        if isinstance(response, str):
            return response
        try:
            return json.dumps(response, ensure_ascii=False)
        except Exception:
            return str(response)

    def _normalize_message_content(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_chunks: List[str] = []
            for item in content:
                text = self._extract_text_from_content_item(item)
                if text:
                    text_chunks.append(text)
            return "".join(text_chunks)
        return str(content)

    def _extract_text_from_content_item(self, item: Any) -> str:
        if item is None:
            return ""
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            if item.get("type") == "text":
                return str(item.get("text", ""))
            if "text" in item:
                return str(item.get("text", ""))
            return ""

        item_type = getattr(item, "type", None)
        if item_type == "text":
            return str(getattr(item, "text", "") or "")
        return str(getattr(item, "text", "") or "")

    def _safe_parse_args(self, arguments: Any) -> Dict[str, Any]:
        if not arguments:
            return {}
        if isinstance(arguments, dict):
            return arguments
        try:
            parsed = json.loads(arguments)
            if isinstance(parsed, dict):
                return parsed
            return {}
        except Exception:
            return {}
