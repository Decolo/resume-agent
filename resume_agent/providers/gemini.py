"""Gemini provider implementation."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, cast

from google import genai
from google.genai import types

from .types import (
    FunctionCall,
    GenerationConfig,
    LLMResponse,
    Message,
    StreamDelta,
    ToolSchema,
)


class GeminiProvider:
    """Google Gemini provider using google-genai SDK."""

    def __init__(
        self,
        api_key: str,
        model: str,
        api_base: str = "",
        search_grounding: bool = False,
    ) -> None:
        self.model = model
        self.search_grounding = search_grounding
        # google-genai does not expose a stable api_base option; keep for future use
        _ = api_base
        self.client = genai.Client(api_key=api_key)

    async def generate(
        self,
        messages: List[Message],
        tools: Optional[List[ToolSchema]],
        config: GenerationConfig,
    ) -> LLMResponse:
        contents = self._to_gemini_contents(messages)
        gemini_tools = self._to_gemini_tools(tools)

        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=config.system_prompt if config.system_prompt else None,
                tools=cast(Any, gemini_tools),
                max_output_tokens=config.max_tokens,
                temperature=config.temperature,
            ),
        )

        return self._from_gemini_response(response)

    async def generate_stream(
        self,
        messages: List[Message],
        tools: Optional[List[ToolSchema]],
        config: GenerationConfig,
    ):
        contents = self._to_gemini_contents(messages)
        gemini_tools = self._to_gemini_tools(tools)

        # generate_content_stream is sync iterator; run it in a thread and buffer
        chunks = await asyncio.to_thread(
            lambda: list(
                self.client.models.generate_content_stream(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=config.system_prompt if config.system_prompt else None,
                        tools=cast(Any, gemini_tools),
                        max_output_tokens=config.max_tokens,
                        temperature=config.temperature,
                    ),
                )
            )
        )

        for chunk in chunks:
            for delta in self._iter_stream_deltas(chunk):
                yield delta

    def _iter_stream_deltas(self, response) -> List[StreamDelta]:
        deltas: List[StreamDelta] = []
        if not response.candidates:
            return deltas
        candidate = response.candidates[0]
        parts = candidate.content.parts if candidate.content else []
        for part in parts or []:
            if part.text:
                deltas.append(StreamDelta(text=part.text))
            elif part.function_call:
                deltas.append(
                    StreamDelta(
                        function_call_start=FunctionCall(
                            name=part.function_call.name,
                            arguments=dict(part.function_call.args) if part.function_call.args else {},
                        )
                    )
                )
        return deltas

    def _from_gemini_response(self, response) -> LLMResponse:
        if not response.candidates:
            raise RuntimeError("Empty LLM response: no candidates")

        candidate = response.candidates[0]
        parts = candidate.content.parts if candidate.content else []
        function_calls: List[FunctionCall] = []
        text_parts: List[str] = []

        for part in parts or []:
            if part.function_call:
                function_calls.append(
                    FunctionCall(
                        name=part.function_call.name,
                        arguments=dict(part.function_call.args) if part.function_call.args else {},
                    )
                )
            elif part.text:
                text_parts.append(part.text)

        return LLMResponse(
            text=" ".join(text_parts).strip(),
            function_calls=function_calls,
            raw=response,
        )

    def _to_gemini_contents(self, messages: List[Message]) -> List[types.Content]:
        contents: List[types.Content] = []
        for msg in messages:
            role = msg.role
            if role == "assistant":
                role = "model"
            elif role == "tool":
                role = "user"

            parts: List[types.Part] = []
            for part in msg.parts:
                if part.text:
                    parts.append(types.Part.from_text(text=part.text))
                elif part.function_call:
                    parts.append(
                        types.Part.from_function_call(
                            name=part.function_call.name,
                            args=part.function_call.arguments,
                        )
                    )
                elif part.function_response:
                    parts.append(
                        types.Part.from_function_response(
                            name=part.function_response.name,
                            response=part.function_response.response,
                        )
                    )

            contents.append(types.Content(role=role, parts=parts))
        return contents

    def _to_gemini_tools(self, tools: Optional[List[ToolSchema]]) -> Optional[List[types.Tool]]:
        gemini_tools: List[types.Tool] = []
        if tools:
            declarations = [self._to_gemini_declaration(tool) for tool in tools]
            if declarations:
                gemini_tools.append(types.Tool(function_declarations=declarations))

        if self.search_grounding:
            gemini_tools.append(types.Tool(google_search=types.GoogleSearch()))

        return gemini_tools or None

    def _to_gemini_declaration(self, tool: ToolSchema) -> types.FunctionDeclaration:
        properties: Dict[str, types.Schema] = {}
        required = tool.parameters.get("required", [])

        for prop_name, prop_def in tool.parameters.get("properties", {}).items():
            properties[prop_name] = self._to_gemini_schema(prop_def or {})

        return types.FunctionDeclaration(
            name=tool.name,
            description=tool.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties=properties,
                required=required,
            ),
        )

    def _to_gemini_schema(self, schema_def: Dict[str, Any]) -> types.Schema:
        type_name = str(schema_def.get("type", "string") or "string").lower()
        type_map = {
            "string": types.Type.STRING,
            "integer": types.Type.INTEGER,
            "number": types.Type.NUMBER,
            "boolean": types.Type.BOOLEAN,
            "object": types.Type.OBJECT,
            "array": types.Type.ARRAY,
        }
        gemini_type = type_map.get(type_name, types.Type.STRING)

        kwargs: Dict[str, Any] = {
            "type": gemini_type,
            "description": schema_def.get("description", ""),
        }

        enum_values = schema_def.get("enum")
        if isinstance(enum_values, list) and enum_values:
            kwargs["enum"] = [str(v) for v in enum_values]

        if gemini_type == types.Type.OBJECT:
            props: Dict[str, types.Schema] = {}
            for prop_name, prop_def in (schema_def.get("properties") or {}).items():
                if isinstance(prop_def, dict):
                    props[prop_name] = self._to_gemini_schema(prop_def)
            kwargs["properties"] = props
            required = schema_def.get("required")
            if isinstance(required, list) and required:
                kwargs["required"] = required

        if gemini_type == types.Type.ARRAY:
            items = schema_def.get("items")
            if isinstance(items, dict):
                kwargs["items"] = self._to_gemini_schema(items)

        return types.Schema(**kwargs)
