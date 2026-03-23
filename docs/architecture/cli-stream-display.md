# CLI Stream Display

Date: 2026-03-23

This note describes the current interactive stream-display design for
`resume-agent`.

## Goal

The CLI should make ongoing work visible without requiring raw token-by-token
rendering.

The target UX is:

1. Users can tell the agent is still working.
2. Tool activity and step progression are visible as they happen.
3. Assistant text keeps advancing during the turn without chunk-noise heuristics.
4. Turn-end output remains stable and readable for later review.

## Display Layers

`resume-agent` now treats interactive display as three separate concerns:

1. **Wire events**
   - Produced by the agent loop (`StepBegin`, `TextDelta`, `ToolCallEvent`,
     `ToolResultEvent`, `ApprovalRequest`, `TurnEnd`).
   - These remain the transport contract between runtime and CLI.
2. **Turn renderer**
   - `resume_agent/cli/stream_display.py`
   - Owns CLI-only live state and final transcript rendering.
   - Appends assistant text, tracks tool states, and manages the Rich `Live`
     lifecycle during a turn.
3. **Interactive shell**
   - `resume_agent/cli/app.py`
   - Still owns prompt handling, approvals, and interrupts.
   - Renders persistent input-adjacent state lines below the prompt.
   - Interactive mode always requests streaming from the agent; there is no
     user-facing `/stream` toggle.

## Input State Lines

The prompt area now shows a compact single-line state bar below the input field
instead of using a right-aligned prompt hint.

It currently includes:

1. remaining context budget
2. active model
3. current workspace

This keeps session state anchored near the input area and avoids splitting
attention between the prompt and the far right edge of the terminal. The bar
uses the terminal default background instead of a filled toolbar background.
The context field is shown as a percentage-left label, for example `98.6% left`,
instead of a raw token count.

## Rendering Policy

The CLI now follows a Kimi-style live rendering model rather than a buffered
chunk flush model:

1. `StepBegin` updates the live view immediately so users can tell work started.
2. `TextDelta` appends directly into the current assistant block.
   Text updates are not force-refreshed on every delta; they ride the fixed
   `Live` refresh cadence to reduce repaint noise during long generations.
   Live rendering only keeps a bounded tail of assistant text so long answers
   do not make the in-flight renderable grow without limit.
3. `ToolCallEvent` creates or updates a live tool-status row.
4. `ToolResultEvent` finalizes the matching tool row with a single-line summary.
5. `ApprovalRequest` pauses the live view while the prompt is shown, then
   resumes the live view afterward.
6. `TurnEnd` closes the live view and prints a stable transcript for the turn.

This keeps the CLI visibly active without relying on magic character thresholds
or line-boundary heuristics.

## Live Status Model

The live area now always shows an animated status line at the top:

1. `Thinking · Step N` when a step has started but no tool or answer text is
   active yet
2. `Running <tool> · Step N` while the latest tool call is still in flight
3. `Writing response · Step N` once assistant text is arriving

This makes idle gaps feel alive even when the model is not emitting visible
text on every refresh tick.

## Final Transcript Rule

The turn renderer owns transcript finalization:

- The live view is transient and only exists while the turn is running.
- When the turn ends, the renderer prints one stable transcript:
  - latest step line
  - tool call lines and tool result summaries
  - one assistant text block
- If no `TextDelta` arrived, `TurnEnd.final_text` is used as the assistant text
  fallback.

This avoids duplicate final panels while preserving a readable conversation
history.

## Testing Strategy

The stream display is verified at two levels:

1. **Renderer behavior tests**
   - live view starts and refreshes as events arrive
   - tool progress and completion states stay readable
   - transcript finalization uses streamed or fallback assistant text correctly
2. **CLI regression test**
   - realistic resume-rewrite prompt
   - step + tool + streamed answer path through `run_interactive()`
   - live updates occur during the turn
   - final transcript contains only one persisted assistant answer
