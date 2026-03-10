# Export Conversation History

The `/export` command allows you to save or copy your conversation history in multiple formats.

## Usage

```bash
/export [target] [format]
```

### Parameters

- **target** (optional, default: `file`)
  - `file` - Save to a file in `exports/` directory
  - `clipboard` or `clip` - Copy to clipboard

- **format** (optional, default: `markdown`)
  - `markdown` or `md` - Markdown format with headers
  - `json` - Structured JSON with metadata
  - `text` or `txt` - Plain text format

## Examples

### Save to File

```bash
# Save as markdown (default)
/export
/export file markdown

# Save as JSON
/export file json

# Save as plain text
/export file text
```

Files are saved to: `exports/conversation_YYYYMMDD_HHMMSS.{ext}`

### Copy to Clipboard

```bash
# Copy markdown to clipboard
/export clipboard markdown
/export clip markdown

# Copy JSON to clipboard
/export clipboard json
/export clip json

# Copy plain text
/export clipboard text
```

## Output Formats

### Markdown Format

```markdown
# Conversation History

## 👤 User

Analyze the resume at examples/resume.md

---

## 🤖 Assistant

I'll analyze your resume...

---
```

### JSON Format

```json
{
  "exported_at": "2026-02-02T12:34:56",
  "agent_mode": "single-agent",
  "messages": [
    {
      "role": "user",
      "parts": [
        {
          "type": "text",
          "content": "Analyze the resume..."
        }
      ]
    },
    {
      "role": "model",
      "parts": [
        {
          "type": "text",
          "content": "I'll analyze the resume and summarize the strongest improvement opportunities."
        }
      ]
    }
  ]
}
```

### Text Format

```
============================================================
User:
============================================================
Analyze the resume at examples/resume.md

============================================================
Assistant:
============================================================
I'll analyze your resume...
```

## Use Cases

### 1. Save for Later Review
```bash
/export file markdown
```
Review the conversation later or share with colleagues.

### 2. Copy for Documentation
```bash
/export clipboard markdown
```
Paste into documentation, tickets, or reports.

### 3. Analyze with External Tools
```bash
/export file json
```
Process the conversation programmatically.

### 4. Quick Share
```bash
/export clip text
```
Copy plain text for quick sharing in chat or email.

## File Location

Exported files are saved to:
```
exports/
├── conversation_20260202_123456.md
├── conversation_20260202_134567.json
└── conversation_20260202_145678.txt
```

The `exports/` directory is automatically created and gitignored.

## Notes

- **Privacy**: Exported files may contain sensitive information. Handle with care.
- **Clipboard**: Requires clipboard access. May not work in some terminal environments.
- **History**: Only exports the current session's conversation history.
