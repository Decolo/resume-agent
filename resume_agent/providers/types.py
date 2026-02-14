"""Provider-agnostic message and tool types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FunctionCall:
    """Represents a tool/function call from the model."""

    name: str
    arguments: Dict[str, Any]
    id: Optional[str] = None


@dataclass
class FunctionResponse:
    """Represents a tool/function response sent back to the model."""

    name: str
    response: Dict[str, Any]
    call_id: Optional[str] = None


@dataclass
class MessagePart:
    """A part of a message: text, tool call, or tool response."""

    text: Optional[str] = None
    function_call: Optional[FunctionCall] = None
    function_response: Optional[FunctionResponse] = None

    @classmethod
    def from_text(cls, text: str) -> "MessagePart":
        return cls(text=text)

    @classmethod
    def from_function_call(cls, call: FunctionCall) -> "MessagePart":
        return cls(function_call=call)

    @classmethod
    def from_function_response(cls, response: FunctionResponse) -> "MessagePart":
        return cls(function_response=response)


@dataclass
class Message:
    """Provider-agnostic chat message."""

    role: str  # "user" | "assistant" | "tool"
    parts: List[MessagePart] = field(default_factory=list)

    @classmethod
    def user(cls, text: str) -> "Message":
        return cls(role="user", parts=[MessagePart.from_text(text)])

    @classmethod
    def assistant(cls, text: str) -> "Message":
        return cls(role="assistant", parts=[MessagePart.from_text(text)])

    @classmethod
    def assistant_tool_calls(cls, calls: List[FunctionCall]) -> "Message":
        return cls(role="assistant", parts=[MessagePart.from_function_call(c) for c in calls])

    @classmethod
    def tool_response(cls, responses: List[FunctionResponse]) -> "Message":
        return cls(role="tool", parts=[MessagePart.from_function_response(r) for r in responses])


@dataclass
class ToolSchema:
    """Tool schema in OpenAI-compatible JSON Schema format."""

    name: str
    description: str
    parameters: Dict[str, Any]


@dataclass
class GenerationConfig:
    """Common generation settings passed to providers."""

    system_prompt: str = ""
    max_tokens: int = 4096
    temperature: Optional[float] = 0.7


@dataclass
class StreamDelta:
    """Single chunk from a streaming response."""

    text: Optional[str] = None
    function_call_start: Optional[FunctionCall] = None
    function_call_delta: Optional[str] = None
    function_call_id: Optional[str] = None
    function_call_index: Optional[int] = None
    function_call_end: bool = False
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None


@dataclass
class LLMResponse:
    """Normalized response from a provider."""

    text: str = ""
    function_calls: List[FunctionCall] = field(default_factory=list)
    usage: Optional[Dict[str, int]] = None
    raw: Any = None
