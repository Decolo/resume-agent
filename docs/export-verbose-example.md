# Export Verbose Feature

The `/export` command now supports a `verbose` option that includes detailed observability logs alongside the conversation history.

## Usage

```bash
# Basic export (conversation only)
/export file markdown

# Verbose export (conversation + observability logs)
/export file markdown verbose
/export file json verbose
/export clipboard text verbose
```

## What's Included in Verbose Mode

### 1. Tool Execution Logs
- Tool name and arguments
- Execution duration (ms)
- Success/failure status
- Cache hit indicator

### 2. LLM API Requests
- Model name
- Step number
- Token usage
- Cost estimation (USD)
- Request duration

### 3. LLM Responses
- Step number
- Response text preview
- Tool calls made

### 4. Error Events
- Error type
- Error message
- Context information

### 5. Step Tracking
- Step start/end events
- Step duration

### 6. Session Statistics
- Total events
- Tool calls count
- Cache hit rate
- LLM requests count
- Total tokens used
- Total cost
- Total duration
- Error count

## Example Output

### Markdown Format (Verbose)

```markdown
# Conversation History

## 👤 User

Parse my resume from resume.md

---

## 🤖 Assistant

I'll parse your resume now.

---

# Observability Logs

- **[14:23:15]** ✓ Tool: `file_read` (45.23ms)
  - Args: `{'path': 'resume.md'}`
- **[14:23:15]** 🤖 LLM Request: `gemini-2.5-flash` (Step 1)
  - Tokens: 1250, Cost: $0.0025, Duration: 234.56ms
- **[14:23:16]** ✓ Tool: `resume_parse` 🔄 (12.34ms)
  - Args: `{'path': 'resume.md', 'format': 'markdown'}`
- **[14:23:16]** 🤖 LLM Request: `gemini-2.5-flash` (Step 2)
  - Tokens: 890, Cost: $0.0018, Duration: 189.23ms

## Session Statistics

- **Total Events:** 8
- **Tool Calls:** 2 (cache hit: 50.0%)
- **LLM Requests:** 2
- **Errors:** 0
- **Total Tokens:** 2,140
- **Total Cost:** $0.0043
- **Total Duration:** 481.36ms
```

### JSON Format (Verbose)

```json
{
  "exported_at": "2026-02-02T14:23:16.123456",
  "agent_mode": "single-agent",
  "messages": [
    {
      "role": "user",
      "parts": [
        {
          "type": "text",
          "content": "Parse my resume from resume.md"
        }
      ]
    },
    {
      "role": "model",
      "parts": [
        {
          "type": "text",
          "content": "I'll parse your resume now."
        }
      ]
    }
  ],
  "observability": {
    "events": [
      {
        "timestamp": "2026-02-02T14:23:15.123456",
        "event_type": "tool_call",
        "data": {
          "tool": "file_read",
          "args": {"path": "resume.md"},
          "result": "# John Doe...",
          "success": true,
          "cached": false
        },
        "duration_ms": 45.23,
        "tokens_used": null,
        "cost_usd": null
      },
      {
        "timestamp": "2026-02-02T14:23:15.234567",
        "event_type": "llm_request",
        "data": {
          "model": "gemini-2.5-flash",
          "step": 1
        },
        "duration_ms": 234.56,
        "tokens_used": 1250,
        "cost_usd": 0.0025
      }
    ],
    "session_stats": {
      "total_tokens": 2140,
      "total_cost_usd": 0.0043,
      "total_duration_ms": 481.36,
      "event_count": 8,
      "tool_calls": 2,
      "llm_requests": 2,
      "errors": 0,
      "cache_hit_rate": 0.5
    }
  }
}
```

### Text Format (Verbose)

```
============================================================
User:
============================================================
Parse my resume from resume.md

============================================================
Assistant:
============================================================
I'll parse your resume now.

============================================================
OBSERVABILITY LOGS
============================================================

[14:23:15] TOOL_CALL
  ✓ Tool: file_read (45.23ms)
  Args: {'path': 'resume.md'}

[14:23:15] LLM_REQUEST
  Model: gemini-2.5-flash
  Step: 1
  Tokens: 1250
  Cost: $0.0025
  Duration: 234.56ms

[14:23:16] TOOL_CALL
  ✓ Tool: resume_parse (12.34ms)
  Args: {'path': 'resume.md', 'format': 'markdown'}

[14:23:16] LLM_REQUEST
  Model: gemini-2.5-flash
  Step: 2
  Tokens: 890
  Cost: $0.0018
  Duration: 189.23ms

============================================================
SESSION STATISTICS
============================================================
Total Events:     8
Tool Calls:       2 (cache hit: 50.0%)
LLM Requests:     2
Errors:           0
Total Tokens:     2,140
Total Cost:       $0.0043
Total Duration:   481.36ms
```

## Use Cases

### 1. Debugging
Export verbose logs to diagnose issues with tool execution or LLM responses.

### 2. Performance Analysis
Analyze token usage, costs, and execution times to optimize agent performance.

### 3. Audit Trail
Maintain detailed records of agent operations for compliance or review.

### 4. Cost Tracking
Monitor API costs across sessions to manage budget.

### 5. Cache Optimization
Identify cache hit rates to tune caching strategies.

## File Naming

Verbose exports include `_verbose` suffix in the filename:

- Regular: `conversation_20260202_142316.md`
- Verbose: `conversation_20260202_142316_verbose.md`

## Notes

- Verbose mode requires observability to be enabled (default: enabled)
- All formats (markdown, json, text) support verbose mode
- Clipboard exports also support verbose mode
- Observability data is collected automatically during agent execution
