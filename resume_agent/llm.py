"""LLM Client - Uses Google GenAI SDK for Gemini with function calling."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

from google import genai
from google.genai import types


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
        
        # Chat history for the session
        self._history: List[types.Content] = []

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
        self._history.append(types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_input)],
        ))
        
        step = 0
        while step < max_steps:
            step += 1
            
            # Generate response
            response = self.client.models.generate_content(
                model=self.config.model,
                contents=self._history,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt if self.system_prompt else None,
                    tools=self._get_tools(),
                    max_output_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                ),
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
            self._history.append(candidate.content)
            
            if function_calls:
                # Execute function calls in parallel
                async def execute_single_tool(fc):
                    """Execute a single tool call and return the response."""
                    func_name = fc.name
                    func_args = dict(fc.args) if fc.args else {}

                    print(f"\n🔧 Tool: {func_name}")
                    print(f"   Args: {json.dumps(func_args, indent=2)[:200]}")

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

                            print(f"   ✅ Result: {result_str[:200]}{'...' if len(result_str) > 200 else ''}")
                        except Exception as e:
                            result_str = f"Error: {str(e)}"
                            print(f"   ❌ {result_str}")
                    else:
                        result_str = f"Error: Unknown tool '{func_name}'"
                        print(f"   ❌ {result_str}")

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
                self._history.append(types.Content(
                    role="user",
                    parts=function_responses,
                ))
            else:
                # No function calls - return the text response
                final_text = "".join(text_parts)
                return final_text
        
        return f"Max steps ({max_steps}) reached."

    def reset(self):
        """Reset conversation history."""
        self._history = []


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
    
    return LLMConfig(
        api_key=data.get("api_key", ""),
        model=data.get("model", "gemini-2.0-flash"),
        max_tokens=data.get("max_tokens", 4096),
        temperature=data.get("temperature", 0.7),
    )
