# Agent Stream Display Reference

Date: 2026-03-22

This note summarizes how three external projects display LLM responses during
streaming:

- Codex
- Kimi CLI
- Vercel AI SDK

It focuses on display behavior, not model quality or tool coverage.

## Short Answer

- Codex supports streaming, but its TUI does not blindly print each token.
  It collects deltas, commits completed lines, and drains them with paced UI
  ticks.
- Kimi CLI supports live streaming in its shell UI. It receives incremental
  wire messages, appends text/tool updates into a Rich `Live` view, and
  refreshes continuously.
- AI SDK provides a full transport-to-UI streaming pipeline. The server emits
  SSE, the client parses incremental chunks, and the chat state updates on each
  text delta.

## 1. Codex

### Display model

Codex has streaming events such as assistant message deltas, reasoning deltas,
and command output deltas. The TUI consumes those deltas, but it renders them
through a staged pipeline instead of raw token writes.

### How the display works

1. Provider or backend emits delta events.
2. The TUI stream controller buffers markdown/text deltas.
3. Only completed logical lines are committed into the render queue.
4. Commit ticks drain the queue smoothly or in catch-up batches.
5. Finalized content becomes transcript history cells.

### Implication

Codex is "real streaming", but the user experience is controlled and
semantic. It optimizes for readability and transcript stability, not for
showing every tiny token immediately.

## 2. Kimi CLI

### Display model

Kimi CLI uses a `Wire` abstraction. The agent emits incremental wire messages,
and different frontends choose whether to consume raw or merged messages.

### How the display works

1. The agent sends `TextPart`, `ThinkPart`, `ToolCallPart`, and other wire
   messages.
2. The shell UI consumes raw wire messages with `merge=False`.
3. A Rich `Live` view keeps a mutable in-memory representation of the current
   response.
4. Each incoming text part is appended to the current content block.
5. The UI schedules a refresh and re-renders the live panel.

### Implication

Kimi CLI is the closest here to "live terminal rendering". But it is still
chunk-based, not guaranteed token-by-token. Its key design choice is that the
interactive shell owns the merge strategy itself.

## 3. Vercel AI SDK

### Display model

AI SDK provides a complete streaming stack from server generation to client UI
state reconciliation.

### How the display works

1. `streamText()` produces an incremental stream of text/tool/reasoning parts.
2. `toUIMessageStreamResponse()` converts the stream to SSE over HTTP.
3. The client transport parses the SSE stream back into UI message chunks.
4. `processUIMessageStream()` handles `text-start`, `text-delta`, and
   `text-end`.
5. Each `text-delta` mutates the in-progress assistant message and writes it
   into chat state immediately.

### Implication

AI SDK supports true end-to-end incremental UI updates, assuming the deployment
environment preserves streaming. It also treats resume, message identity, and
duplicate prevention as first-class streaming concerns.

## Comparison

| Project | What streams | How it is displayed | UX style |
| --- | --- | --- | --- |
| Codex | Deltas and event items | Buffered, line-committed, tick-drained TUI | Semantic streaming |
| Kimi CLI | Wire messages | Live terminal view updated per chunk | Live interactive streaming |
| AI SDK | SSE UI chunks | Client chat state updates per delta | End-to-end stateful streaming |

## Takeaway for Resume Agent

If `resume-agent` keeps a stream mode, the bar should not be "can print while
the model is generating". The more important question is:

1. Are streamed chunks truly incremental?
2. Does the UI avoid duplicate final output?
3. Is the render cadence readable instead of noisy?
4. Can message identity, resume, and stop behavior remain coherent?

The external references suggest that good streaming UX is not a single switch.
It is a coordinated design across protocol, buffering, rendering, and
completion semantics.
