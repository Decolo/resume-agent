# PI-Mono History Design Reference

Snapshot date: 2026-03-01

This note summarizes design learnings from `badlogic/pi-mono` for agent history
management, with direct mapping to this repository.

## Why This Matters

In coding agents, history is not always linear:

1. retries create alternate paths
2. branch switching should preserve context
3. long sessions must compact without losing auditability

`pi-mono` solves this by separating:

- persistent history storage
- model prompt context materialization

## Mental Model

Storage uses a tree. Prompting uses a list.

```text
History Store (tree)                    Prompt Context (list)

root                                    [root -> ... -> current leaf]
 └─ node A
    └─ node B
       ├─ node C1 (attempt 1)           model sees only one active path
       └─ node C2 (attempt 2)
```

This keeps all attempts recoverable while keeping each model call simple.

## PI-Mono Pattern (Observed)

### 1. Append-only entries with parent pointers

- History entries are persisted as append-only records.
- Each record includes identity and ancestry, so branch history is explicit.
- No destructive rewrite is required when forking or retrying.

### 2. Leaf-based active branch

- Runtime points to a current leaf.
- The active prompt is built from root to that leaf.
- Branch change only moves the leaf pointer, then rematerializes context.

### 3. Compaction as first-class history entries

- Compaction does not delete meaning.
- A compaction entry stores summary information and the keep boundary.
- Old raw history remains auditable; active context stays within token budget.

### 4. Branch summarization on branch changes

- When leaving one branch for another, summarized context can be injected.
- This avoids "branch amnesia" while still keeping branch separation.

### 5. Hook points around session operations

- Extension hooks can intercept compaction/tree operations.
- This allows custom policy without rewriting the core loop.

## ASCII Data Flow

```text
User input
   |
   v
Agent loop
   |
   +--> append message/tool records
   |
   +--> token budget check
          |
          +--> over budget?
                 |
                 +--> create compaction entry (summary + keep boundary)
                 |
                 +--> continue from compacted active path
   |
   v
build context from current leaf path
   |
   v
LLM call
```

## Comparison With Our Current Design

| Topic | Current repo | PI-mono learning |
| --- | --- | --- |
| Storage shape | Linear list in memory/session JSON | Tree-capable ancestry model |
| Budget handling | Sliding window + token pruning | Summary-based compaction entries |
| Retry/alternate attempts | Kept inline in list | Natural branch representation |
| Session replay | Full message list replay | Path replay + branch-aware semantics |
| Extensibility | Limited to manager behavior | Hook-based session interception |

## Practical Takeaways For Resume-Agent

1. Keep the current message API stable for now.
2. Introduce a history entry schema with `entry_id`, `parent_id`, and
   `entry_type`.
3. Add a context builder that materializes only active path messages.
4. Add compaction entries before considering full branch UI/commands.
5. Preserve auditability by keeping compaction metadata in persisted sessions.

## Cautions

1. Tree storage increases debugging complexity without proper inspection tools.
2. Summary quality directly affects long-session reliability.
3. Migration from list sessions should be additive and reversible.
