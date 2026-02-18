"""Test raw streaming mode."""

import asyncio

from packages.core.resume_agent_core.agent_factory import create_agent
from packages.core.resume_agent_core.llm import load_config


async def main():
    config = load_config()
    agent = create_agent(config)

    print("=" * 80)
    print("Testing RAW streaming - each delta.text will be shown with repr()")
    print("=" * 80)

    chunk_count = 0
    prev_text = ""

    def on_delta(delta):
        nonlocal chunk_count, prev_text
        if delta.text:
            chunk_count += 1
            print(f"\n[Chunk {chunk_count}]")
            print(f"  delta.text = {repr(delta.text)}")
            print(f"  len = {len(delta.text)}")
            if delta.text == prev_text:
                print("  ⚠️  DUPLICATE!")
            prev_text = delta.text

    result = await agent.run("Say hello in one short sentence", stream=True, on_stream_delta=on_delta)

    print(f"\n\n{'=' * 80}")
    print(f"Total chunks: {chunk_count}")
    print(f"Final text: {result}")


if __name__ == "__main__":
    asyncio.run(main())
