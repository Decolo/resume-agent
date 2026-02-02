# Session Persistence

Phase 3 adds conversation persistence to Resume Agent, allowing you to save and restore sessions across runs.

## Overview

Session persistence enables:
- **Save/Load Sessions**: Preserve conversation history, agent state, and observability data
- **Auto-Save**: Automatically save after tool executions (configurable)
- **Session Management**: List, load, and delete sessions via CLI commands
- **Full State Restoration**: Restore conversation history, observability events, and multi-agent state
- **Multi-Agent Support**: Serialize delegation history, shared context, and agent statistics

## Quick Start

### Basic Usage

```bash
# Start the agent
uv run resume-agent

# Have a conversation
You: Parse my resume from resume.pdf

# Save the session
/save my_resume_analysis

# Later, restore the session
/load session_20260202_143022_my_resume_analysis

# Continue the conversation with full context
You: Now improve the work experience section
```

### List and Manage Sessions

```bash
# List all saved sessions
/sessions

# Delete a session
/delete-session session_20260202_143022

# Enable auto-save
/auto-save on
```

## CLI Commands

### `/save [name]`

Save the current session to a JSON file.

```bash
/save                    # Auto-generated ID
/save my_resume_v1       # Custom name
```

**Session ID Format**: `session_YYYYMMDD_HHMMSS_[name]_[uuid]`

**Storage Location**: `workspace/sessions/`

### `/load <session_id>`

Load a previously saved session.

```bash
/load session_20260202_143022_my_resume_v1_abc123
```

**Restores**:
- Full conversation history
- Observability events (tool calls, LLM requests, errors)
- Multi-agent state (delegation history, shared context)

### `/sessions`

List all saved sessions with metadata.

**Displays**:
- Session ID
- Created/Updated timestamps
- Agent mode (single-agent or multi-agent)
- Message count
- Total tokens used

### `/delete-session <session_id>`

Delete a saved session.

```bash
/delete-session session_20260202_143022
```

### `/auto-save [on|off]`

Toggle auto-save after tool execution.

```bash
/auto-save on     # Enable auto-save
/auto-save off    # Disable auto-save
/auto-save        # Show current status
```

**Note**: Auto-save triggers after each tool execution, not after every message.

## Session File Format

Sessions are stored as JSON files in `workspace/sessions/`:

```json
{
  "schema_version": "1.0",
  "session": {
    "id": "session_20260202_143022_abc123",
    "created_at": "2026-02-02T14:30:22.123456",
    "updated_at": "2026-02-02T14:35:45.654321",
    "mode": "multi-agent",
    "workspace_dir": "/path/to/workspace",
    "config": {
      "model": "gemini-2.5-flash",
      "max_tokens": 4096,
      "temperature": 0.7
    }
  },
  "conversation": {
    "messages": [
      {
        "role": "user",
        "parts": [
          {"type": "text", "content": "Hello"}
        ]
      },
      {
        "role": "model",
        "parts": [
          {"type": "function_call", "name": "file_read", "args": {...}}
        ]
      },
      {
        "role": "user",
        "parts": [
          {"type": "function_response", "name": "file_read", "response": "..."}
        ]
      }
    ],
    "max_messages": 50,
    "max_tokens": 100000
  },
  "observability": {
    "events": [
      {
        "timestamp": "2026-02-02T14:30:22.123456",
        "event_type": "tool_call",
        "data": {"tool": "file_read", "args": {...}},
        "duration_ms": 100.5,
        "tokens_used": null,
        "cost_usd": null
      }
    ],
    "session_stats": {
      "event_count": 42,
      "tool_calls": 15,
      "llm_requests": 10,
      "errors": 0,
      "total_tokens": 12450,
      "total_cost_usd": 0.0099,
      "cache_hit_rate": 0.33
    }
  },
  "multi_agent": {
    "delegation_history": [
      {
        "task_id": "task_123",
        "from_agent": "orchestrator_agent",
        "to_agent": "parser_agent",
        "timestamp": "2026-02-02T14:30:25.000000",
        "duration_ms": 1500.0,
        "success": true
      }
    ],
    "agent_stats": {...},
    "shared_context": {
      "data": {...},
      "history": [...]
    }
  }
}
```

## Configuration

Edit `config/config.yaml` or `config/config.local.yaml`:

```yaml
# Session persistence (Phase 3)
session:
  enabled: true
  auto_save: false  # Auto-save after tool execution
  sessions_dir: "./sessions"  # Relative to workspace_dir
```

## Architecture

### Components

1. **SessionSerializer**: Converts agent state to/from JSON
   - `serialize_message()`: Gemini `types.Content` → JSON
   - `deserialize_message()`: JSON → `types.Content`
   - `serialize_history()`: Full conversation history
   - `serialize_observability()`: Events + session stats
   - `serialize_multi_agent_state()`: Delegation, context, agent stats

2. **SessionManager**: Manages session lifecycle
   - `save_session()`: Save current session to JSON file
   - `load_session()`: Load session from JSON file
   - `list_sessions()`: List all sessions with metadata
   - `delete_session()`: Delete a session file
   - `restore_agent_state()`: Reconstruct agent state from JSON

3. **SessionIndex**: Fast session lookup
   - `.index.json`: Metadata cache for quick listing
   - Sorted by `updated_at` (most recent first)

### Storage Structure

```
workspace/
├── sessions/                          # Session files directory
│   ├── session_20260202_143022.json  # Auto-saved session
│   ├── session_20260202_150000.json
│   └── .index.json                    # Session index for quick lookup
├── exports/                           # Existing export directory
└── resumes/                           # User's resume files
```

### Auto-Save Flow

1. User sends a message
2. Agent processes and calls tools
3. After tool execution completes:
   - If `auto_save_enabled` is `True`
   - `SessionManager.save_session()` is called
   - Session is saved to `sessions/` directory
   - Index is updated

### Restoration Flow

1. User runs `/load <session_id>`
2. `SessionManager.load_session()` reads JSON file
3. `SessionManager.restore_agent_state()` reconstructs:
   - Conversation history → `HistoryManager._history`
   - Observability events → `AgentObserver.events`
   - Multi-agent state → `DelegationManager`, `SharedContext`
4. Agent continues with full context

## Use Cases

### Resume Iteration Workflow

```bash
# Session 1: Initial analysis
uv run resume-agent
You: Parse and analyze my resume
/save resume_analysis_v1

# Session 2: Improvements
uv run resume-agent
/load resume_analysis_v1
You: Improve the work experience section
/save resume_improvements_v2

# Session 3: Final formatting
uv run resume-agent
/load resume_improvements_v2
You: Convert to HTML format
/save resume_final_v3
```

### Long-Running Tasks

```bash
# Enable auto-save for long sessions
/auto-save on

# Work on complex resume improvements
You: Parse my resume and improve all sections

# Session is automatically saved after each tool call
# If interrupted, restart and /load to continue
```

### Experimentation

```bash
# Save before trying different approaches
/save before_experiment

# Try approach A
You: Rewrite in a more technical style
/save approach_a

# Revert and try approach B
/load before_experiment
You: Rewrite in a more business-focused style
/save approach_b

# Compare results
/sessions
```

## Troubleshooting

### Session Not Found

**Error**: `❌ Session not found: session_xyz`

**Solution**:
- Use `/sessions` to list available sessions
- Check session ID spelling
- Verify `workspace/sessions/` directory exists

### Failed to Save Session

**Error**: `❌ Failed to save session: [error]`

**Possible Causes**:
- Insufficient disk space
- Permission issues on `sessions/` directory
- Corrupted session data

**Solution**:
```bash
# Check disk space
df -h

# Check permissions
ls -la workspace/sessions/

# Create sessions directory if missing
mkdir -p workspace/sessions
```

### Failed to Load Session

**Error**: `❌ Failed to load session: [error]`

**Possible Causes**:
- Corrupted JSON file
- Schema version mismatch
- Missing required fields

**Solution**:
```bash
# Validate JSON syntax
cat workspace/sessions/session_xyz.json | python -m json.tool

# Check schema version
grep schema_version workspace/sessions/session_xyz.json

# If corrupted, delete and start fresh
/delete-session session_xyz
```

### Auto-Save Not Working

**Symptoms**: Sessions not saving automatically

**Checklist**:
1. Verify auto-save is enabled: `/auto-save`
2. Check if tools are being executed (auto-save triggers after tool calls)
3. Verify `SessionManager` is initialized in CLI
4. Check for errors in console output

## Performance Considerations

### Session File Size

- **Typical Size**: 10-100 KB per session
- **Large Sessions**: 1-5 MB (with extensive history)
- **Recommendation**: Delete old sessions periodically

### Auto-Save Overhead

- **Trigger**: After tool execution (not every message)
- **Duration**: ~10-50ms for typical sessions
- **Impact**: Minimal (async I/O)

### Index Performance

- **Lookup**: O(1) for metadata retrieval
- **List All**: O(n log n) for sorting by timestamp
- **Recommendation**: Keep < 100 sessions for optimal performance

## Security Considerations

### File Permissions

Session files should be user-readable only:

```bash
# Set restrictive permissions
chmod 600 workspace/sessions/*.json
chmod 700 workspace/sessions/
```

### Sensitive Data

**Warning**: Sessions may contain:
- Resume content (PII: names, addresses, phone numbers)
- File paths
- Tool execution logs

**Recommendations**:
- Do not commit `sessions/` to version control
- Add to `.gitignore`:
  ```
  workspace/sessions/
  ```
- Encrypt sessions if storing in cloud storage

### Session Expiration

Consider implementing auto-deletion:

```bash
# Delete sessions older than 30 days
find workspace/sessions/ -name "session_*.json" -mtime +30 -delete
```

## Migration from Phase 2

Phase 3 is **fully backward compatible** with Phase 2:

- ✅ All existing functionality preserved
- ✅ No breaking changes to CLI or API
- ✅ Session persistence is opt-in (disabled by default)
- ✅ Works with both single-agent and multi-agent modes

**To enable**:
1. Update `config/config.yaml`: `session.enabled: true`
2. Optionally enable auto-save: `session.auto_save: true`
3. Use `/save`, `/load`, `/sessions` commands

## Next Steps (Phase 4)

After Phase 3, Phase 4 will add multi-provider support:
- OpenAI API support (GPT-4, GPT-4o)
- Claude API support (Claude 3.5 Sonnet, Opus)
- DeepSeek API support
- Provider-agnostic abstraction layer
- Cost comparison across providers

## API Reference

### SessionSerializer

```python
from resume_agent.session import SessionSerializer

# Serialize a message
msg = types.Content(role="user", parts=[...])
serialized = SessionSerializer.serialize_message(msg)

# Deserialize a message
msg = SessionSerializer.deserialize_message(serialized)

# Serialize history
history_data = SessionSerializer.serialize_history(history_manager)

# Serialize observability
obs_data = SessionSerializer.serialize_observability(observer)
```

### SessionManager

```python
from resume_agent.session import SessionManager

# Initialize
session_manager = SessionManager(workspace_dir="./workspace")

# Save session
session_id = session_manager.save_session(
    agent=agent,
    session_name="my_session",
    auto_save=False
)

# Load session
session_data = session_manager.load_session(session_id)

# Restore agent state
session_manager.restore_agent_state(agent, session_data)

# List sessions
sessions = session_manager.list_sessions()

# Delete session
session_manager.delete_session(session_id)
```

### SessionIndex

```python
from resume_agent.session import SessionIndex

# Initialize
index = SessionIndex(index_path=Path("sessions/.index.json"))

# Add session
index.add_session(session_id, metadata)

# Get metadata
metadata = index.get_session_metadata(session_id)

# List all
sessions = index.list_all()

# Remove session
index.remove_session(session_id)
```
