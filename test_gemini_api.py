#!/usr/bin/env python3
"""
Simple test script to verify Gemini API accessibility
"""

import asyncio
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from resume_agent.llm import GeminiAgent, LLMConfig
from google import genai
from google.genai import types


async def test_basic_connection():
    """Test basic API connection"""
    print("=" * 60)
    print("Testing Gemini API Connection")
    print("=" * 60)

    # Load config
    try:
        import yaml
        config_path = Path(__file__).parent / "config" / "config.yaml"
        with open(config_path) as f:
            config_data = yaml.safe_load(f)

        api_key = config_data.get("api_key", "")
        model = config_data.get("model", "gemini-2.0-flash")

        print(f"\n✓ Config loaded")
        print(f"  Model: {model}")
        print(f"  API Key: {api_key[:20]}..." if api_key else "  API Key: NOT SET")

    except Exception as e:
        print(f"\n✗ Failed to load config: {e}")
        return False

    if not api_key:
        print("\n✗ API key not set in config/config.yaml")
        print("  Please set your Gemini API key in config/config.yaml")
        return False

    # Test 1: Initialize client
    print("\n" + "-" * 60)
    print("Test 1: Initialize Gemini client")
    print("-" * 60)

    try:
        client = genai.Client(api_key=api_key)
        print("✓ Client initialized successfully")
    except Exception as e:
        print(f"✗ Failed to initialize client: {e}")
        return False

    # Test 2: Simple generation (no tools)
    print("\n" + "-" * 60)
    print("Test 2: Simple text generation")
    print("-" * 60)

    try:
        print("Sending request: 'Say hello'")
        response = client.models.generate_content(
            model=model,
            contents="Say hello"
        )

        if response and response.text:
            print(f"✓ Response received: {response.text[:100]}")
        else:
            print(f"✗ Empty response: {response}")
            return False

    except Exception as e:
        print(f"✗ Generation failed: {e}")
        print(f"  Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

    # Test 3: Generation with function calling
    print("\n" + "-" * 60)
    print("Test 3: Generation with function calling")
    print("-" * 60)

    try:
        # Define a simple tool
        test_tool = types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="get_time",
                    description="Get current time",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={},
                        required=[]
                    )
                )
            ]
        )

        print("Sending request with tool: 'What time is it?'")
        response = client.models.generate_content(
            model=model,
            contents="What time is it?",
            config=types.GenerateContentConfig(
                tools=[test_tool],
                temperature=0.7
            )
        )

        if response:
            if response.candidates and response.candidates[0].content.parts:
                part = response.candidates[0].content.parts[0]
                if hasattr(part, 'function_call'):
                    print(f"✓ Function call received: {part.function_call.name}")
                elif hasattr(part, 'text'):
                    print(f"✓ Text response: {part.text[:100]}")
                else:
                    print(f"✓ Response received: {part}")
            else:
                print(f"✗ Unexpected response format: {response}")
                return False
        else:
            print(f"✗ Empty response")
            return False

    except Exception as e:
        print(f"✗ Function calling test failed: {e}")
        print(f"  Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

    # Test 4: Test with GeminiAgent
    print("\n" + "-" * 60)
    print("Test 4: Test with GeminiAgent class")
    print("-" * 60)

    try:
        config = LLMConfig(
            api_key=api_key,
            model=model,
            max_tokens=1000,
            temperature=0.7
        )

        agent = GeminiAgent(config)
        print("✓ GeminiAgent initialized")

        # Simple test without tools
        print("Sending request: 'Say hello in one sentence'")
        response = await agent.run("Say hello in one sentence", max_steps=1)

        if response:
            print(f"✓ Agent response: {response[:100]}")
        else:
            print(f"✗ Empty agent response")
            return False

    except Exception as e:
        print(f"✗ GeminiAgent test failed: {e}")
        print(f"  Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    result = asyncio.run(test_basic_connection())
    sys.exit(0 if result else 1)
