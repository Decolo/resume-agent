# Troubleshooting Guide

This document contains solutions to common issues encountered when using Resume Agent.

## Table of Contents

- [Gemini API Errors](#gemini-api-errors)
- [Installation Issues](#installation-issues)
- [File Parsing Issues](#file-parsing-issues)
- [Performance Issues](#performance-issues)

---

## Gemini API Errors

### Error: "Please ensure that function response turn comes immediately after a function call turn"

**Error Message:**
```
400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'Please ensure that
function response turn comes immediately after a function call turn.',
'status': 'INVALID_ARGUMENT'}}
```

**Root Cause:**

This error occurs when the conversation history sent to the Gemini API violates the function calling protocol. The Gemini API requires that:

1. A model message containing a `function_call` (role="model")
2. Must be **immediately followed** by a user message containing the `function_response` (role="user")

These two messages must be adjacent and cannot be separated by other messages.

**What Causes This:**

The `HistoryManager` class automatically prunes conversation history when it exceeds limits (50 messages or 100k tokens). The pruning logic removes messages from the beginning of the history without checking if it's breaking function call/response pairs.

**Scenario Example:**

```python
# Original history:
[user, model_with_function_call, user_with_function_response, model, user, ...]

# After pruning (removes first message):
[model_with_function_call, user_with_function_response, model, user, ...]  # ✓ OK

# After more pruning (removes function_call but keeps response):
[user_with_function_response, model, user, ...]  # ✗ BROKEN - orphaned response

# Or removes response but keeps call:
[model_with_function_call, model, user, ...]  # ✗ BROKEN - orphaned call
```

**Technical Details:**

The issue is in `resume_agent/llm.py`:

1. **Line 279**: Model response (with function calls) is added to history
2. **Lines 362-366**: Function responses are added as a user message
3. **Line 38**: Every message addition triggers `_prune_if_needed()`
4. **Lines 48-61**: Pruning logic removes messages without pair awareness

The pruning can happen:
- Between adding the function call and function response
- When removing historical messages, breaking existing pairs

**Solution:**

The fix implements **pair-aware pruning** that:
1. Detects function call/response pairs in the history
2. Removes pairs together (both or neither)
3. Never breaks the adjacency requirement

**Workaround (Temporary):**

If you encounter this error before the fix is applied:

1. **Increase history limits** in `llm.py:137`:
   ```python
   self.history_manager = HistoryManager(max_messages=100, max_tokens=200000)
   ```

2. **Reset conversation more frequently** using `/reset` command in CLI

3. **Use shorter prompts** to reduce token usage

**Fixed In:** Version 0.2.0+ (Phase 1 improvements)

---

### Error: "GEMINI_API_KEY not set"

**Error Message:**
```
ValueError: GEMINI_API_KEY not set
```

**Solution:**

1. Set the API key in `config/config.yaml`:
   ```yaml
   api_key: "your-gemini-api-key-here"
   ```

2. Or set as environment variable:
   ```bash
   export GEMINI_API_KEY="your-gemini-api-key-here"
   ```

3. Or use environment variable substitution in config:
   ```yaml
   api_key: "${GEMINI_API_KEY}"
   ```

---

### Error: "429 RESOURCE_EXHAUSTED" (Rate Limit)

**Error Message:**
```
429 RESOURCE_EXHAUSTED. Rate limit exceeded
```

**Solution:**

The retry logic will automatically handle this with exponential backoff. If it persists:

1. **Reduce request frequency** - Add delays between requests
2. **Check your API quota** - Visit Google AI Studio
3. **Upgrade your API tier** - If using free tier, consider paid tier

The retry configuration in `llm.py:238-244` will attempt 3 times with exponential backoff (1s, 2s, 4s).

---

## Installation Issues

### PyMuPDF Installation Fails

**Error:**
```
ERROR: Could not build wheels for pymupdf
```

**Solution:**

1. **macOS**: Install system dependencies
   ```bash
   brew install mupdf
   pip install pymupdf
   ```

2. **Linux**: Install system dependencies
   ```bash
   sudo apt-get install libmupdf-dev
   pip install pymupdf
   ```

3. **Windows**: Use pre-built wheels
   ```bash
   pip install --upgrade pip
   pip install pymupdf
   ```

---

### python-docx Installation Issues

**Error:**
```
ImportError: python-docx not installed
```

**Solution:**

```bash
pip install python-docx
```

Note: The package name is `python-docx` but imported as `docx`:
```python
from docx import Document  # Correct
```

---

## File Parsing Issues

### Error: "File too large" (10MB limit)

**Error Message:**
```
Error: File size exceeds 10MB limit
```

**Solution:**

The `file_read` tool has a 10MB size limit for security. For large files:

1. **Split the file** into smaller chunks
2. **Use resume_parse** instead - it has no size limit for PDFs/DOCX
3. **Compress the file** if it's a text format

---

### Error: "Binary file detected"

**Error Message:**
```
Error: Cannot read binary file
```

**Solution:**

The `file_read` tool only reads text files. For binary formats:

1. **Use resume_parse** for PDF/DOCX files
2. **Convert to text format** first
3. **Use appropriate tool** for the file type

---

### PDF Parsing Returns Garbled Text

**Symptoms:**
- Extracted text is unreadable
- Special characters appear as boxes
- Text order is incorrect

**Solutions:**

1. **Check PDF format** - Some PDFs are scanned images, not text
2. **Use OCR** - For image-based PDFs, use OCR tools first
3. **Try different parser** - Convert to DOCX and parse that instead
4. **Check encoding** - Ensure PDF uses standard fonts

---

## Performance Issues

### Slow Response Times

**Symptoms:**
- Agent takes a long time to respond
- Tool execution is slow

**Solutions:**

1. **Check cache hit rate** - View cache statistics after each run
   ```
   Cache Statistics:
   - Total requests: 10
   - Cache hits: 7 (70.0%)
   ```

2. **Increase cache TTL** in `cache.py:8-12`:
   ```python
   TOOL_CACHE_CONFIG = {
       "file_read": 120,      # Increase from 60s
       "file_list": 60,       # Increase from 30s
       "resume_parse": 600,   # Increase from 300s
   }
   ```

3. **Reduce max_steps** in `config/config.yaml`:
   ```yaml
   max_steps: 30  # Reduce from 50
   ```

4. **Use faster model**:
   ```yaml
   model: "gemini-2.0-flash"  # Faster than gemini-1.5-pro
   ```

---

### High Token Usage / Cost

**Symptoms:**
- Estimated cost is high
- Token usage exceeds expectations

**Solutions:**

1. **Enable history pruning** - Already enabled by default
2. **Reduce max_tokens** in config:
   ```yaml
   max_tokens: 2048  # Reduce from 4096
   ```

3. **Use more concise prompts**
4. **Reset conversation** frequently with `/reset`
5. **Check session summary** for token breakdown:
   ```
   Session Summary:
   - Total tokens: 45,234
   - Estimated cost: $0.0036
   ```

---

### Memory Usage Issues

**Symptoms:**
- High memory consumption
- Out of memory errors

**Solutions:**

1. **Reduce history limits** in `llm.py:137`:
   ```python
   self.history_manager = HistoryManager(max_messages=30, max_tokens=50000)
   ```

2. **Clear cache periodically**:
   ```python
   agent.agent.cache.clear()
   ```

3. **Reset conversation** with `/reset` command

---

## Bash Tool Security Errors

### Error: "Dangerous command blocked"

**Error Message:**
```
Error: Command contains dangerous patterns: rm -rf
```

**Solution:**

The bash tool blocks dangerous commands for security. Blocked patterns include:
- `rm`, `dd`, `mkfs`, `sudo`, `curl`, `wget`
- Shell operators: `;`, `&&`, `||`, `|`, `` ` ``, `$(`, `${`, `>`, `>>`

**Workarounds:**

1. **Use file tools** instead:
   - Use `file_write` instead of `echo > file`
   - Use `file_read` instead of `cat file`
   - Use `file_list` instead of `ls`

2. **Break down commands** - Use multiple safe commands instead of piped commands

3. **Request specific operations** - Ask the agent to use appropriate tools

---

## Getting Help

If you encounter an issue not covered here:

1. **Check logs** - Look for detailed error messages in console output
2. **Enable verbose mode** - Run with `--verbose` flag
3. **Check configuration** - Use `/config` command in CLI
4. **Review session summary** - Check token usage and cache statistics
5. **Report issues** - Open an issue at https://github.com/your-repo/resume-agent/issues

---

## Debug Mode

To enable detailed debugging:

1. **Set log level** in `config/config.yaml`:
   ```yaml
   log_level: "DEBUG"
   ```

2. **Check observability logs** - Review `AgentObserver` output for:
   - Tool execution times
   - Cache hit rates
   - Token usage per step
   - Error details

3. **Inspect history** - Add debug prints in `llm.py`:
   ```python
   print(f"History length: {len(self.history_manager.get_history())}")
   for i, msg in enumerate(self.history_manager.get_history()):
       print(f"  {i}: role={msg.role}, parts={len(msg.parts)}")
   ```

---

## Version Information

- **Current Version**: 0.1.0
- **Python Version**: 3.8+
- **Gemini API**: google-genai >= 1.0.0
- **Last Updated**: 2026-01-26
