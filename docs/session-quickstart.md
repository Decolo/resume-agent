# Quick Start: Session Persistence

## TL;DR - Auto-Save is Enabled by Default

**Good news!** Your sessions are now automatically saved after every tool execution. You don't need to do anything special.

## How It Works

1. **Start the agent** (auto-save is enabled by default):
   ```bash
   uv run resume-agent
   ```

2. **Work normally** - sessions are saved automatically:
   ```
   You: Parse my resume from resume.pdf
   # Session auto-saved after parsing

   You: Improve the work experience section
   # Session auto-saved after improvements
   ```

3. **If you close unexpectedly**, your work is saved!

4. **To resume**, just restart and load the latest session:
   ```bash
   uv run resume-agent
   /sessions          # See all saved sessions
   /load <session_id> # Load the most recent one
   ```

## Quick Commands

```bash
/sessions              # List all saved sessions (sorted by most recent)
/load <session_id>     # Restore a previous session
/save my_custom_name   # Manually save with a custom name
```

## Finding Your Latest Session

Sessions are automatically sorted by most recent first:

```bash
/sessions

# Output shows:
┌─────────────────────────────────────┬──────────────────┬──────────────────┬─────────────┬──────────┬────────┐
│ Session ID                          │ Created          │ Updated          │ Mode        │ Messages │ Tokens │
├─────────────────────────────────────┼──────────────────┼──────────────────┼─────────────┼──────────┼────────┤
│ session_20260202_150000_abc123     │ 2026-02-02 15:00 │ 2026-02-02 15:05 │ auto-agent  │ 8        │ 2,100  │
│ session_20260202_143022_def456     │ 2026-02-02 14:30 │ 2026-02-02 14:35 │ auto-agent  │ 12       │ 3,450  │
└─────────────────────────────────────┴──────────────────┴──────────────────┴─────────────┴──────────┴────────┘
                                       ↑ Top row is your most recent session
```

## Session Storage Location

Sessions are stored in your workspace:

```bash
workspace/
└── sessions/
    ├── session_20260202_150000_abc123.json  # Most recent
    ├── session_20260202_143022_def456.json
    └── .index.json  # Metadata cache
```

## Configuration

Auto-save is always enabled when session persistence is active:

```yaml
session:
  enabled: true
  sessions_dir: "./sessions"
```

## Best Practices

1. **Let auto-save do its job** - You don't need to manually save unless you want a named checkpoint
2. **Use custom names for important milestones**: `/save client_acme_final_v1`
3. **Clean up old sessions periodically**: `/delete-session <old_session_id>`
4. **Check `/sessions` after restart** to find your latest work

## Troubleshooting

### "I closed without saving, can I recover?"

✅ **Yes!** If auto-save was enabled (default), your session was saved automatically. Just:
```bash
/sessions
/load <most_recent_session_id>
```

### "How do I know if auto-save is working?"

You'll see sessions appearing in your `workspace/sessions/` directory after tool executions. Use `/sessions` to list them.

### "I want to disable auto-save"

Auto-save is always on when session persistence is enabled. To stop saving sessions entirely, disable session persistence in your config:

```yaml
# In config/config.yaml:
session:
  enabled: false
```

## Example Workflow

```bash
# Day 1: Start working
uv run resume-agent
You: Parse my resume from resume.pdf
You: Improve the summary section
/quit  # Auto-saved!

# Day 2: Resume work
uv run resume-agent
/sessions  # See yesterday's session at the top
/load session_20260202_150000_abc123
You: Now improve the work experience section
/quit  # Auto-saved again!

# Day 3: Continue
uv run resume-agent
/sessions
/load session_20260203_100000_xyz789  # Yesterday's session
You: Convert to HTML format
/save final_version  # Manual save with custom name
```

## What Gets Saved

Every auto-saved session includes:
- ✅ Full conversation history
- ✅ Tool execution results
- ✅ LLM requests and responses
- ✅ Observability data (tokens, costs, cache hits)
- ✅ Multi-agent state (if using multi-agent mode)

## Summary

**You don't need to do anything special!** Auto-save is enabled by default, so your work is always protected. Just use `/sessions` and `/load` to resume previous conversations.
