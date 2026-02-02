# User-Friendly Session Management

## What Changed

Session management is now much more user-friendly with:
- ✅ **Numbered sessions** - Use `/load 1` instead of long session IDs
- ✅ **Interactive picker** - `/load` shows all sessions to choose from
- ✅ **Custom names displayed** - See your custom names instead of UUIDs
- ✅ **Simplified commands** - Delete by number: `/delete-session 1`

## Visual Examples

### 1. Listing Sessions (New Look)

**Before:**
```
┌─────────────────────────────────────┬──────────────────┬──────────────────┬─────────────┬──────────┬────────┐
│ Session ID                          │ Created          │ Updated          │ Mode        │ Messages │ Tokens │
├─────────────────────────────────────┼──────────────────┼──────────────────┼─────────────┼──────────┼────────┤
│ session_20260202_143022_my_resume...│ 2026-02-02 14:30 │ 2026-02-02 14:35 │ auto-agent  │ 12       │ 3,450  │
└─────────────────────────────────────┴──────────────────┴──────────────────┴─────────────┴──────────┴────────┘
```

**After:**
```
📁 Saved Sessions
┌───┬──────────────────────────┬────────────────┬────────────────┬────────────┬──────────┬──────────┐
│ # │ Name                     │ Created        │ Updated        │ Mode       │ Messages │ Tokens   │
├───┼──────────────────────────┼────────────────┼────────────────┼────────────┼──────────┼──────────┤
│ 1 │ my_resume_final          │ 02-02 15:00    │ 02-02 15:05    │ auto-agent │ 12       │ 3,450    │
│ 2 │ client_acme_v1           │ 02-02 14:30    │ 02-02 14:35    │ auto-agent │ 8        │ 2,100    │
│ 3 │ session_20260202_120000  │ 02-02 12:00    │ 02-02 12:10    │ auto-agent │ 5        │ 1,200    │
└───┴──────────────────────────┴────────────────┴────────────────┴────────────┴──────────┴──────────┘

💡 Quick load: /load <number>  (e.g., /load 1 for most recent)
```

### 2. Loading Sessions (Interactive Picker)

**Command:** `/load` (without arguments)

**Output:**
```
📁 Available Sessions:
────────────────────────────────────────────────────────────────────────────────
┌───┬──────────────────────────┬────────────────┬────────────┬──────┬──────────┐
│ # │ Name                     │ Updated        │ Mode       │ Msgs │ Tokens   │
├───┼──────────────────────────┼────────────────┼────────────┼──────┼──────────┤
│ 1 │ my_resume_final          │ 02-02 15:05    │ auto-agent │ 12   │ 3,450    │
│ 2 │ client_acme_v1           │ 02-02 14:35    │ auto-agent │ 8    │ 2,100    │
│ 3 │ session_20260202_120000  │ 02-02 12:10    │ auto-agent │ 5    │ 1,200    │
└───┴──────────────────────────┴────────────────┴────────────┴──────┴──────────┘

💡 Usage: /load <number> or /load <full_session_id>
   Example: /load 1  (loads the most recent session)
```

### 3. Quick Load by Number

**Before:**
```
/load session_20260202_143022_my_resume_final_abc123
✓ Session loaded: session_20260202_143022_my_resume_final_abc123
```

**After:**
```
/load 1
✓ Session loaded: 12 messages, 3,450 tokens
```

### 4. Saving with Custom Name

**Before:**
```
/save my_resume_final
✓ Session saved: session_20260202_150000_my_resume_final_abc123
```

**After:**
```
/save my_resume_final
✓ Session saved as: my_resume_final
   Use /load to restore this session later
```

### 5. Deleting Sessions

**Before:**
```
/delete-session session_20260202_143022_my_resume_final_abc123
✓ Session deleted: session_20260202_143022_my_resume_final_abc123
```

**After:**
```
/delete-session 1
✓ Session deleted
```

## Complete Workflow Example

```bash
# Start the agent
uv run resume-agent

╔═══════════════════════════════════════════════════════════╗
║                    📄 Resume Agent                        ║
║         AI-powered Resume Modification Assistant          ║
╠═══════════════════════════════════════════════════════════╣
║  Quick Commands:                                          ║
║    /help     - Show all commands                          ║
║    /save     - Save current session                       ║
║    /load     - Load a previous session (shows picker)     ║
║    /sessions - List all saved sessions                    ║
║    /quit     - Exit the agent                             ║
║                                                           ║
║  💡 Auto-save is enabled - your work is protected!        ║
╚═══════════════════════════════════════════════════════════╝

✓ Auto-save enabled (sessions saved after tool execution)
🤖 Running in auto-agent mode

# Work on your resume
📝 You: Parse my resume from resume.pdf
🤖 Assistant: [analyzes resume...]

📝 You: Improve the work experience section
🤖 Assistant: [provides improvements...]

# Save with a custom name
📝 You: /save my_resume_v1
✓ Session saved as: my_resume_v1
   Use /load to restore this session later

# Exit
📝 You: /quit
👋 Goodbye!

# ─────────────────────────────────────────────────────────

# Later: Restart and resume
uv run resume-agent

# Show all sessions
📝 You: /sessions

📁 Saved Sessions
┌───┬──────────────────────────┬────────────────┬────────────────┬────────────┬──────────┬──────────┐
│ # │ Name                     │ Created        │ Updated        │ Mode       │ Messages │ Tokens   │
├───┼──────────────────────────┼────────────────┼────────────────┼────────────┼──────────┼──────────┤
│ 1 │ my_resume_v1             │ 02-02 15:00    │ 02-02 15:05    │ auto-agent │ 12       │ 3,450    │
│ 2 │ client_acme              │ 02-02 14:30    │ 02-02 14:35    │ auto-agent │ 8        │ 2,100    │
└───┴──────────────────────────┴────────────────┴────────────────┴────────────┴──────────┴──────────┘

💡 Quick load: /load <number>  (e.g., /load 1 for most recent)

# Load by number
📝 You: /load 1
✓ Session loaded: 12 messages, 3,450 tokens

# Continue where you left off
📝 You: Now convert to HTML format
🤖 Assistant: [converts with full context...]
```

## Key Improvements

### 1. **Numbered Sessions**
- Sessions are numbered 1, 2, 3... (most recent first)
- Use `/load 1` to load the most recent session
- No need to copy/paste long session IDs

### 2. **Custom Names Displayed**
- If you saved with `/save my_resume_v1`, you see "my_resume_v1" in the list
- If you didn't provide a name, you see the timestamp
- Much easier to identify your sessions

### 3. **Interactive Picker**
- `/load` without arguments shows all sessions
- Pick the one you want by number
- See message count and tokens to help identify

### 4. **Simplified Delete**
- `/delete-session 1` deletes session #1
- No need to copy the full session ID

### 5. **Better Feedback**
- Save: "✓ Session saved as: my_resume_v1"
- Load: "✓ Session loaded: 12 messages, 3,450 tokens"
- Clear, concise, informative

## Command Comparison

| Task | Old Command | New Command |
|------|-------------|-------------|
| List sessions | `/sessions` | `/sessions` (better display) |
| Load session | `/load session_20260202_143022_abc123` | `/load 1` |
| Load interactively | N/A | `/load` (shows picker) |
| Delete session | `/delete-session session_20260202_143022_abc123` | `/delete-session 1` |
| Save with name | `/save my_resume` | `/save my_resume` (better feedback) |

## Tips

1. **Use `/load` without arguments** to see all sessions and pick one
2. **Use custom names** when saving: `/save project_name_v1`
3. **Session #1 is always the most recent** - quick to load
4. **Auto-save is enabled by default** - you're always protected
5. **Check `/sessions` regularly** to see what you have saved

## Technical Details

### Session ID Format
- **With custom name**: `session_20260202_150000_my_resume_v1_abc123`
- **Without custom name**: `session_20260202_150000_abc123`

### Display Logic
- Extracts custom name from session ID
- Shows custom name if present, otherwise shows timestamp
- Truncates long names for better display
- Sorts by updated timestamp (most recent first)

### Number Assignment
- Numbers are assigned dynamically based on sort order
- #1 is always the most recently updated session
- Numbers may change as you create/delete sessions
- Use numbers for quick access, full IDs for scripts
