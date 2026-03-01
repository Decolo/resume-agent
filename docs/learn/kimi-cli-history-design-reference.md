# Kimi CLI History Design Reference

Snapshot date: 2026-03-01

This note summarizes history/session design learnings from `MoonshotAI/kimi-cli`
and highlights differences from `pi-mono` and this repository.

## What Kimi CLI Optimizes For

Kimi CLI emphasizes:

1. session-level persistence
2. predictable context-size control
3. replay/debug visibility

Its documented shape is closer to linear session logs with compaction, instead
of a tree-first history model.

## Data Layout (Session Scope)

```text
~/.kimi/
└─ sessions/
   └─ <work-dir-hash>/
      └─ <session-id>/
         ├─ context.jsonl   # conversation/context messages
         ├─ wire.jsonl      # protocol/event log for replay and debugging
         └─ state.json      # runtime state (approval, subagents, dirs, etc.)
```

Each session is isolated by directory and ID. Session switching (`--session`,
`--continue`, `/sessions`) happens at this level.

## Context Window Control

Kimi CLI docs expose an explicit threshold formula:

```text
if context_tokens + reserved_context_size >= max_context_size:
    trigger compaction
```

Compaction can be automatic or manually triggered with `/compact`.

## Compaction Behavior (Documented)

1. Long context is summarized/compacted.
2. Compaction is used as token-budget control before hard overflow.
3. `/clear` clears conversation context but keeps runtime session state.

## Contrast With PI-Mono

| Topic | Kimi CLI (docs) | PI-mono (code/docs) |
| --- | --- | --- |
| Session shape | Linear context log per session | Tree entries (`id`/`parentId`) |
| Branch semantics | Session-level switch/fork | In-session branch navigation |
| Budget control | `reserved_context_size` threshold | `contextWindow - reserveTokens` |
| Overflow strategy | Auto/manual compact | Auto compact + overflow recovery path |
| Persistence files | `context.jsonl`, `wire.jsonl`, `state.json` | Session entries in tree-aware storage |

## Takeaways For Resume-Agent

1. Threshold-based pre-compaction is a practical baseline.
2. Keep context data and runtime state logically separated.
3. Provide explicit operator commands for context management (`compact`,
   `clear`, `sessions` style lifecycle).

## Sources

- Sessions guide: <https://moonshotai.github.io/kimi-cli/en/guides/sessions.html>
- Data locations: <https://moonshotai.github.io/kimi-cli/en/configuration/data-locations.html>
- Config files (`max_context_size`, `reserved_context_size`):
  <https://moonshotai.github.io/kimi-cli/en/configuration/config-files.html>
- Slash commands (`/compact`, `/clear`, `/sessions`):
  <https://moonshotai.github.io/kimi-cli/en/reference/slash-commands.html>
- Wire mode and replay: <https://moonshotai.github.io/kimi-cli/en/customization/wire-mode.html>
- Changelog: <https://moonshotai.github.io/kimi-cli/en/release-notes/changelog.html>
