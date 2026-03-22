# Session Persistence

Session persistence stores conversation state in `workspace/sessions/` so a
later `/resume` continues from the last saved state instead of starting from an
empty history.

This document describes the current implementation after the turn-tree and
compaction refactor.

## Overview

Session persistence currently provides:

- Auto-save after assistant/tool progress updates the session state.
- `/resume` to browse and restore saved sessions.
- `/compact` to compress older history and persist the compacted state.
- `/delete-session <id>` to remove one saved session.
- `/clear-sessions` to remove all saved sessions.

When a session has already been compacted, `/resume` restores the compacted
history, not the original raw transcript that was truncated away.

## Quick Start

```bash
# Start the CLI with a workspace
uv run resume-agent --workspace ./examples/my_resume

# Have a conversation
You: Parse my resume and improve the summary section

# Force compaction if the session is getting long
/compact

# Later, restore the saved session
/resume

# Continue from the restored state
You: Now create an HTML version
```

## CLI Commands

### `/resume [query]`

Open the inline session picker and restore one saved session.

```bash
/resume
/resume backend
```

What gets restored:

- The active prompt history used for the next LLM request.
- Turn-tree metadata used to rebuild the active path.
- Compaction state and compaction checkpoints.
- Observability data and session stats.
- Runtime-specific state when that runtime supports it.

### `/compact`

Force history compaction immediately.

The CLI prints:

- `covered_messages`
- `checkpoints`
- `summary_chunks`
- `active_history_messages`

If compaction changed the active history, the updated session snapshot is saved
immediately.

### `/delete-session <session_id>`

Delete one saved session JSON file.

```bash
/delete-session session_20260320_233443_6907d063
```

### `/clear-sessions`

Delete all saved session files and reset the session index.

```bash
/clear-sessions
```

## Persistence Model

The runtime now persists more than a flat `messages` array.

### 1. Materialized Active History

This is the exact history that will be sent on the next provider call.

After compaction it usually looks like:

```text
[COMPRESSION_STATE] summary message
recent raw tail turn(s)
```

The first item is a synthetic assistant message that contains the structured
summary state in prompt form.

### 2. Turn Tree

Conversation history is stored internally as user-anchored turns rather than as
only one flat list.

Each turn tracks:

- `turn_id`
- `parent_turn_id`
- `messages`
- token estimate
- whether the turn contains tool calls or tool responses

This lets the runtime compact complete turn prefixes without cutting through the
middle of a user turn.

### 3. Compression State

Compaction uses anchored iterative summarization.

That means:

- only the newly compacted span is summarized
- the prior summary is reused as context for the next compaction
- the runtime merges structured fields instead of regenerating one full summary
  from scratch every time

Current structured fields:

- `summary_chunks`
- `session_intent`
- `file_modifications`
- `decisions`
- `open_questions`
- `next_steps`

### 4. Compaction Checkpoints

Each compaction records a checkpoint with coverage metadata so the runtime knows
how much history has already been summarized.

Each checkpoint stores:

- `checkpoint_id`
- `covered_messages`
- `compacted_messages`
- `summary_text`

## Session File Format

Session files now use schema `2.0`.

Simplified example:

```json
{
  "schema_version": "2.0",
  "session": {
    "id": "session_20260320_233443_6907d063",
    "created_at": "2026-03-20T23:34:43.000000",
    "updated_at": "2026-03-20T23:41:02.000000",
    "workspace_dir": "/path/to/workspace"
  },
  "conversation": {
    "max_messages": 50,
    "max_tokens": 100000,
    "history_format": "turn_tree_v1",
    "reserve_tokens": 0,
    "tail_tokens": 512,
    "current_leaf_turn_id": "turn_7",
    "active_start_turn_id": "turn_5",
    "turns": [
      {
        "turn_id": "turn_5",
        "parent_turn_id": "turn_4",
        "messages": [
          {"role": "user", "parts": [{"type": "text", "content": "..." }]}
        ],
        "token_estimate": 123,
        "contains_tool_call": false,
        "contains_tool_response": false
      }
    ],
    "compression_state": {
      "version": 1,
      "covered_messages": 23,
      "summary_chunks": ["..."],
      "session_intent": "Generate and refine the resume outputs",
      "file_modifications": ["frontend-resume-optimized-2026-03-20.md"],
      "decisions": ["Use compacted history on resume"],
      "open_questions": [],
      "next_steps": ["Generate HTML version"]
    },
    "compaction_checkpoints": [
      {
        "checkpoint_id": 1,
        "covered_messages": 23,
        "compacted_messages": 23,
        "summary_text": "..."
      }
    ]
  }
}
```

## Compaction Behavior

Compaction is intended to run before the provider hard-fails on context size.

Trigger rule:

```text
estimated_context_tokens + reserve_tokens >= model_context_window
```

Current behavior:

- Keep a recent raw tail controlled by `tail_tokens`.
- Compact only the older active prefix.
- Preserve tool-call integrity by compacting at turn boundaries.
- Materialize the result back into prompt history as one
  `[COMPRESSION_STATE]` summary item plus the raw tail.
- If the provider still reports context overflow, the runtime gets one forced
  compaction retry path before surfacing the error.

## Restore Behavior

When `/resume` loads a compacted session:

1. the turn tree is restored
2. the compression state is restored
3. the materialized active history is rebuilt
4. the CLI shows compaction metadata before printing the recent history preview

This is why a resumed compacted session shows a compaction summary item at the
top instead of replaying the full old transcript.

## Compatibility

Old pre-refactor session files are not supported by the new turn-tree restore
path.

If you still have old sessions created before the schema `2.0` format, clear
them and start fresh:

```bash
/clear-sessions
```

## Troubleshooting

### Resume fails with unsupported history format

This means the session file predates the current turn-tree persistence format.

Fix:

```bash
/clear-sessions
```

### `/compact` reports nothing eligible for compaction

The active history is still short enough that no older prefix needs to be
summarized yet.

### You want to verify a session was compacted

Use `/resume` and look for the compaction panel:

- `covered_messages > 0`
- `checkpoints >= 1`
- first history preview row starts with `[COMPRESSION_STATE]`
