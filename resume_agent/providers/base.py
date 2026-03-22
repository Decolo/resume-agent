"""Provider protocol definition."""

from __future__ import annotations

from typing import AsyncIterator, List, Optional, Protocol

from .types import GenerationConfig, LLMResponse, Message, ModelCapabilities, StreamDelta, ToolSchema


class ChatProvider(Protocol):
    """Protocol for provider implementations."""

    def get_model_capabilities(self) -> ModelCapabilities: ...

    async def generate(
        self,
        messages: List[Message],
        tools: Optional[List[ToolSchema]],
        config: GenerationConfig,
    ) -> LLMResponse: ...

    async def generate_stream(
        self,
        messages: List[Message],
        tools: Optional[List[ToolSchema]],
        config: GenerationConfig,
    ) -> AsyncIterator[StreamDelta]: ...
