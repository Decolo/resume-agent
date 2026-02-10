# Session Persistence Troubleshooting

## Common Issues and Solutions

### Issue: "Input should be a valid dictionary" Error

**Error Message:**
```
❌ Failed to load session: 1 validation error for FunctionResponse
response
  Input should be a valid dictionary
```

**Cause:**
This error occurs when loading sessions created with an older version that serialized function responses as strings instead of dictionaries.

**Solution:**
This has been fixed in the latest version. The deserializer now handles both formats:
- If the response is a string, it wraps it in `{"result": "..."}`
- If the response is already a dict, it uses it directly

**If you still see this error:**
1. Update to the latest version
2. Delete old sessions: `/delete-session <number>`
3. Create new sessions with the fixed version

### Issue: Session ID Too Long to Type

**Problem:**
Session IDs like `session_20260202_143022_my_resume_final_abc123` are hard to type.

**Solution:**
Use numbered sessions instead:
```bash
/sessions  # See all sessions with numbers
/load 1    # Load session #1 (most recent)
```

### Issue: Can't Find My Session

**Problem:**
You saved a session but can't find it in `/sessions`.

**Solutions:**

1. **Check if you're in the right workspace:**
   ```bash
   /config  # Shows current workspace
   ```
   Sessions are stored per workspace in `workspace/sessions/`

2. **List sessions manually:**
   ```bash
   ls -lt workspace/sessions/
   ```

3. **Check if sessions directory exists:**
   ```bash
   ls -la workspace/sessions/
   ```
   If it doesn't exist, sessions haven't been saved yet.

### Issue: Auto-Save Not Working

**Problem:**
Sessions aren't being saved automatically.

**Solutions:**

1. **Check config file:**
   ```yaml
   # config/config.yaml
   session:
     enabled: true
   ```

2. **Verify auto-save triggers:**
   Auto-save only triggers after tool execution, not after every message.
   Try a command that uses tools:
   ```
   You: List files in workspace
   # This uses file_list tool, should trigger auto-save
   ```

### Issue: Session Load Fails with "Session not found"

**Problem:**
```
❌ Session not found: session_xyz
```

**Solutions:**

1. **Use the interactive picker:**
   ```bash
   /load  # Shows all available sessions
   ```

2. **Check session number:**
   ```bash
   /sessions  # See all sessions with numbers
   /load 1    # Use the number, not the full ID
   ```

3. **Verify session file exists:**
   ```bash
   ls workspace/sessions/session_*.json
   ```

### Issue: "AutoAgent object has no attribute 'agent'" Error

**Problem:**
```
❌ Failed to save session: 'AutoAgent' object has no attribute 'agent'
```

**Cause:**
This was a bug in the initial implementation when using auto-routing mode (`multi_agent.enabled: "auto"`).

**Solution:**
This has been fixed. Update to the latest version. The `AutoAgent` class now exposes `.agent` and `.llm_agent` attributes for session management.

### Issue: Session File Corrupted

**Problem:**
Session file exists but won't load.

**Solutions:**

1. **Validate JSON syntax:**
   ```bash
   cat workspace/sessions/session_xyz.json | python -m json.tool
   ```

2. **Check schema version:**
   ```bash
   grep schema_version workspace/sessions/session_xyz.json
   # Should show: "schema_version": "1.0"
   ```

3. **If corrupted, delete and start fresh:**
   ```bash
   /delete-session <number>
   ```

### Issue: Too Many Sessions

**Problem:**
You have hundreds of old sessions cluttering the list.

**Solutions:**

1. **Delete old sessions manually:**
   ```bash
   /sessions
   /delete-session 10  # Delete session #10
   /delete-session 11  # Delete session #11
   ```

2. **Delete old sessions via filesystem:**
   ```bash
   # Delete sessions older than 30 days
   find workspace/sessions/ -name "session_*.json" -mtime +30 -delete

   # Rebuild index
   rm workspace/sessions/.index.json
   # Index will be rebuilt automatically on next /sessions command
   ```

3. **Keep only recent sessions:**
   ```bash
   # Keep only the 10 most recent sessions
   cd workspace/sessions/
   ls -t session_*.json | tail -n +11 | xargs rm
   ```

### Issue: Session Restore Incomplete

**Problem:**
Session loads but conversation history seems incomplete.

**Possible Causes:**

1. **History was pruned before saving:**
   The agent automatically prunes history to stay under limits (50 messages, 100k tokens).
   This is normal behavior.

2. **Session was saved mid-conversation:**
   If you saved during a multi-step operation, some context might be missing.

**Solutions:**
- Save at natural breakpoints (after completing a task)
- Use custom names to mark complete sessions: `/save task_complete_v1`

### Issue: Performance Degradation

**Problem:**
Agent becomes slow with many sessions.

**Solutions:**

1. **Clean up old sessions:**
   Keep < 100 sessions for optimal performance.

2. **Check session file sizes:**
   ```bash
   du -sh workspace/sessions/*.json | sort -h
   ```
   Large sessions (> 5MB) may slow down loading.

## Getting Help

If you encounter issues not covered here:

1. **Check the logs:**
   Look for error messages in the console output

2. **Verify your setup:**
   ```bash
   /config  # Check configuration
   ls -la workspace/sessions/  # Check session files
   ```

3. **Report the issue:**
   Include:
   - Error message
   - Steps to reproduce
   - Session file (if relevant)
   - Config settings

## Best Practices to Avoid Issues

1. ✅ **Use custom names for important sessions:** `/save project_v1`
2. ✅ **Load by number, not full ID:** `/load 1`
3. ✅ **Clean up old sessions regularly:** `/delete-session <number>`
4. ✅ **Auto-save is always on:** Sessions are saved automatically after tool execution
5. ✅ **Save at natural breakpoints:** After completing tasks
6. ✅ **Check `/sessions` before loading:** See what's available
7. ✅ **Use `/load` without arguments:** Interactive picker is easier
