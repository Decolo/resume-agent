"""Compatibility wrapper for provider-agnostic message and tool types."""

from __future__ import annotations

from packages.providers.resume_agent_providers.types import (
    FunctionCall,
    FunctionResponse,
    GenerationConfig,
    LLMResponse,
    Message,
    MessagePart,
    StreamDelta,
    ToolSchema,
)

__all__ = [
    "FunctionCall",
    "FunctionResponse",
    "GenerationConfig",
    "LLMResponse",
    "Message",
    "MessagePart",
    "StreamDelta",
    "ToolSchema",
]
