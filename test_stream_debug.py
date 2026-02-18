"""Debug streaming: log every delta to a file so we can see what's happening."""

import asyncio
import json
import time

from dotenv import load_dotenv

from packages.core.resume_agent_core.agent_factory import create_agent
from packages.core.resume_agent_core.llm import load_config


async def main():
    load_dotenv()
    config = load_config()
    agent = create_agent(config)

    log_entries = []
    chunk_idx = 0

    def on_delta(delta):
        nonlocal chunk_idx
        chunk_idx += 1
        entry = {
            "idx": chunk_idx,
            "ts": round(time.time(), 3),
            "text": getattr(delta, "text", None),
            "text_repr": repr(getattr(delta, "text", None)),
            "fc_start": str(getattr(delta, "function_call_start", None)),
            "fc_delta": getattr(delta, "function_call_delta", None),
            "fc_end": getattr(delta, "function_call_end", None),
            "finish": getattr(delta, "finish_reason", None),
        }
        log_entries.append(entry)
        # Also print to terminal for quick view
        if entry["text"]:
            print(f"[{chunk_idx:3d}] text={entry['text_repr']}")

    print("Sending: 'say hello in one sentence'")
    print("=" * 60)

    response = await agent.run(
        "say hello in one sentence",
        stream=True,
        on_stream_delta=on_delta,
    )

    print("\n" + "=" * 60)
    print(f"Total deltas: {chunk_idx}")
    print(f"Final response: {response!r}")

    # Write full log
    with open("stream_debug_log.json", "w", encoding="utf-8") as f:
        json.dump(log_entries, f, indent=2, ensure_ascii=False)
    print("\nFull log written to stream_debug_log.json")


if __name__ == "__main__":
    asyncio.run(main())
