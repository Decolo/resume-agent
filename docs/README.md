# Resume Agent Documentation

Welcome to the Resume Agent documentation! This guide will help you get started with the AI-powered resume modification assistant.

## 📚 Documentation Structure

### Getting Started
- **[Quick Start](./quick-start.md)** - Get up and running in 3 steps
- **[Getting Started Guide](./getting-started.md)** - Comprehensive setup and configuration
- **[How to Run](./how-to-run.md)** - Multiple ways to launch the agent

### Architecture & Development
- **[Architecture Overview](../.claude/CLAUDE.md)** - System design and components (Claude Code instructions)
- **[Phase 1 Improvements](./architecture/phase1-improvements.md)** - Detailed technical improvements
- **[API Reference](./api-reference/phase1-quick-reference.md)** - Code examples and API usage

### Workspace & Examples
- **Examples Folder** - Sample resumes and outputs live in `../examples/`

---

## 🚀 Quick Navigation

### I want to...

**Start using the agent immediately**
→ Go to [Quick Start](./quick-start.md)

**Understand how to set up and configure**
→ Go to [Getting Started Guide](./getting-started.md)

**Learn about different ways to run the agent**
→ Go to [How to Run](./how-to-run.md)

**Understand the system architecture**
→ Go to [Architecture Overview](../.claude/CLAUDE.md)

**Learn about Phase 1 improvements (retry, caching, etc.)**
→ Go to [Phase 1 Improvements](./architecture/phase1-improvements.md)

**See code examples and API usage**
→ Go to [API Reference](./api-reference/phase1-quick-reference.md)

**Use the example workspace with your resume**
→ See the `../examples/` folder for sample inputs

---

## 📋 What is Resume Agent?

Resume Agent is an AI-powered assistant that helps you:

- **Parse** resumes in multiple formats (PDF, DOCX, Markdown, JSON, TXT)
- **Analyze** your resume for strengths and weaknesses
- **Improve** content with stronger action verbs and metrics
- **Tailor** your resume for specific job positions
- **Convert** between different formats (HTML, JSON, Markdown)
- **Save** multiple versions for different applications

### Supported Formats

**Input:** PDF, DOCX, Markdown, TXT, JSON
**Output:** Markdown, HTML, JSON, TXT

---

## ⚡ Phase 1 Features

The agent now includes powerful improvements:

1. **Automatic Retry Logic** - Handles temporary failures gracefully
2. **Parallel Execution** - Multiple operations run concurrently (2-3x faster)
3. **Smart Caching** - Remembers previous results (10x+ faster for repeated ops)
4. **History Management** - Automatic conversation pruning
5. **Structured Observability** - Detailed logging and session statistics
6. **Enhanced Security** - File size limits, binary detection, command blocklist

---

## 🎯 Common Workflows

### Workflow 1: Analyze and Improve
```
1. Parse your resume
2. Get analysis and feedback
3. Improve specific sections
4. Save the improved version
```

### Workflow 2: Tailor for Job
```
1. Parse your resume
2. Provide job description
3. Tailor resume for the role
4. Save tailored version
```

### Workflow 3: Format Conversion
```
1. Parse your resume
2. Convert to desired format
3. Save in new format
```

---

## 🔧 Available Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands and example prompts |
| `/files` | List all files in workspace |
| `/reset` | Clear conversation history |
| `/config` | Show current configuration |
| `/quit` or `/exit` | Exit the agent |

---

## 📊 Session Statistics

After each session, you'll see detailed statistics:

```
============================================================
SESSION SUMMARY
============================================================
Total Events:     15
Tool Calls:       8 (cache hit: 37.5%)
LLM Requests:     2
Errors:           0
Total Tokens:     2,450
Total Cost:       $0.0196
Total Duration:   3,245.67ms
============================================================

============================================================
CACHE STATISTICS
============================================================
Cache Hits:       3
Cache Misses:     5
Hit Rate:         37.5%
Cache Size:       3 entries
============================================================
```

---

## 🆘 Troubleshooting

### Command not found: resume-agent
Use `uv run` prefix:
```bash
uv run resume-agent --workspace ./examples/my_resume
```

### File not found
Make sure your resume is in the workspace directory:
```bash
cp /path/to/your/resume.pdf ./examples/my_resume/resume.pdf
```

### File too large
Files must be under 10MB. Convert to text if needed:
```bash
pdftotext resume.pdf resume.txt
```

### Command blocked for safety
Some bash commands are blocked for security. Use only safe commands like `ls`, `cat`, `grep`.

---

## 📖 Documentation Files

- **docs/README.md** - This file (main index)
- **docs/quick-start.md** - 3-step quick start guide
- **docs/getting-started.md** - Comprehensive setup guide
- **docs/how-to-run.md** - Multiple ways to run the agent
- **.claude/CLAUDE.md** - Architecture and technical details
- **docs/architecture/phase1-improvements.md** - Phase 1 improvements details
- **docs/api-reference/phase1-quick-reference.md** - API reference with code examples
- **examples/** - Sample resumes and example workspace

---

## 🚀 Next Steps

1. **Start with [Quick Start](./quick-start.md)** - Get running in 3 steps
2. **Copy your resume** to the workspace
3. **Run the agent** and start improving your resume
4. **Review [Getting Started Guide](./getting-started.md)** for more details
5. **Check [Architecture Overview](../.claude/CLAUDE.md)** to understand how it works

---

## 💡 Tips for Best Results

1. **Start with Analysis** - Ask the agent to parse and analyze your resume first
2. **Be Specific** - Instead of "improve my resume", say "improve my work experience section"
3. **Use Multiple Turns** - Break tasks into steps: analyze → improve → format → save
4. **Provide Context** - Include job descriptions when tailoring
5. **Review Changes** - Always review the agent's suggestions
6. **Save Versions** - Keep different versions for different roles

---

## 📞 Support

For issues or questions:
- Check `/help` command in the agent
- Review the relevant documentation file
- Check the troubleshooting section above

Happy resume improving! 🎉
