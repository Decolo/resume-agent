# Resume Agent - Quick Start for Your Resume

## 🚀 Start Here (3 Steps)

### Step 1: Copy Your Resume to Workspace

```bash
# Navigate to the project directory
cd /Users/decolo/Github/resume-agent

# Copy your resume to workspace
cp /path/to/your/resume.pdf ./examples/my_resume/resume.pdf

# Or if you prefer to use current directory
cp /path/to/your/resume.pdf ./resume.pdf
```

**Supported formats:**
- `.pdf` (PDF files)
- `.docx` (Word documents)
- `.md` (Markdown)
- `.txt` (Plain text)
- `.json` (JSON Resume format)

### Step 2: Start the Agent

```bash
# Interactive mode (recommended for testing)
uv run resume-agent --workspace ./examples/my_resume

# Or simply
uv run resume-agent
```

You'll see the welcome banner:
```
╔═══════════════════════════════════════════════════════════╗
║                    📄 Resume Agent                        ║
║         AI-powered Resume Modification Assistant          ║
╠═══════════════════════════════════════════════════════════╣
║  Commands:                                                ║
║    /help     - Show this help message                     ║
║    /reset    - Reset conversation                         ║
║    /quit     - Exit the agent                             ║
║    /files    - List files in workspace                    ║
╚═══════════════════════════════════════════════════════════╝
```

### Step 3: Start Improving Your Resume

Type your requests at the `📝 You:` prompt.

---

## 📝 Example Session

Here's what a typical session looks like:

```
📝 You: Parse my resume from resume.pdf

🤖 Assistant:
=== Resume Content ===
[Your resume content here]

=== Detected Sections ===
[summary]
[experience]
[education]
[skills]

📝 You: Improve my work experience section with stronger action verbs

🤖 Assistant:
I've enhanced your work experience section with stronger action verbs:

**Before:**
- Worked on backend systems
- Helped with database optimization

**After:**
- Architected and deployed scalable backend systems
- Optimized database queries, reducing latency by 40%

📝 You: Add quantifiable metrics to my achievements

🤖 Assistant:
I've added specific metrics to your achievements:

**Before:**
- Led a team of engineers

**After:**
- Led a team of 8 engineers, delivering 5 major features
- Improved system performance by 35%, reducing costs by $200K annually

📝 You: Save the improved version to improved_resume.md

🤖 Assistant:
✅ Successfully saved improved resume to improved_resume.md

📝 You: /files

📁 Workspace Files
file    1024    resume.pdf
file    2048    improved_resume.md

📝 You: /quit

👋 Goodbye!
```

---

## 💡 Suggested Workflow for Your Resume

### Phase 1: Analysis (5 minutes)

```
📝 You: Parse my resume from resume.pdf and analyze it
```

The agent will:
- Extract all sections
- Identify strengths and weaknesses
- Suggest improvements

### Phase 2: Enhancement (10 minutes)

```
📝 You: Improve my work experience section with stronger action verbs
📝 You: Add quantifiable metrics to my achievements
📝 You: Enhance my skills section with industry keywords
```

### Phase 3: Tailoring (5 minutes)

```
📝 You: Tailor my resume for a [Job Title] position at [Company]
```

Or provide a job description:

```
📝 You: Here's a job description I'm applying for:
[Paste job description]

Now tailor my resume to match these requirements
```

### Phase 4: Formatting (5 minutes)

```
📝 You: Convert my resume to HTML format
📝 You: Save as resume_final.html
```

### Phase 5: Review

```
📝 You: /files
```

Check the generated files in your workspace.

---

## 🎯 Useful Prompts for Your Resume

### Analysis & Feedback
```
"Parse my resume from resume.pdf and analyze it"
"Check if my resume is ATS-friendly"
"Identify gaps in my resume"
"What are the strongest parts of my resume?"
"What should I improve in my resume?"
```

### Improvement & Enhancement
```
"Improve my work experience section with stronger action verbs"
"Add quantifiable metrics to my achievements"
"Enhance my skills section"
"Make my professional summary more compelling"
"Rewrite my objective statement"
"Add more specific accomplishments"
```

### Tailoring & Customization
```
"Tailor my resume for a Senior Software Engineer position"
"Customize my resume for a Data Science role at Google"
"Adjust my resume to match this job description: [paste job description]"
"Highlight relevant skills for a Product Manager role"
"Reorder my sections to emphasize relevant experience"
```

### Format Conversion
```
"Convert my resume to HTML format"
"Convert my resume to JSON format"
"Convert my resume to plain text"
"Save my resume as resume_formatted.md"
"Create a one-page version of my resume"
```

### Specific Edits
```
"Rewrite my cover letter"
"Add a projects section"
"Reorganize my resume sections"
"Remove outdated information"
"Expand my education section"
```

---

## 📊 What You'll See

### Session Summary (Automatic)

After each session, you'll see:

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

This shows:
- **Performance**: How fast operations completed
- **Reliability**: Any errors encountered
- **Cost**: Estimated API cost
- **Caching**: How many operations were cached

---

## 🔧 Commands During Session

| Command | What It Does |
|---------|-------------|
| `/help` | Show available commands and example prompts |
| `/files` | List all files in your workspace |
| `/reset` | Start a new conversation (clear history) |
| `/config` | Show current configuration |
| `/quit` or `/exit` | Exit the agent |

---

## 💾 Output Files

After running the agent, you'll have:

```
workspace/
├── resume.pdf                 # Your original resume
├── improved_resume.md         # Improved version (Markdown)
├── resume_final.html          # HTML version
├── resume.json                # JSON version
└── resume_tailored.md         # Tailored for specific job
```

You can download and use any of these versions!

---

## ⚡ Performance Features (Phase 1)

The agent now includes:

1. **Automatic Retry** - Handles temporary failures
2. **Parallel Execution** - Multiple operations at once (2-3x faster)
3. **Smart Caching** - Remembers previous results (10x+ faster for repeated ops)
4. **History Pruning** - Keeps conversations manageable
5. **Detailed Logging** - See exactly what's happening

---

## 🆘 Troubleshooting

### "File not found: resume.pdf"
```bash
# Check what files are in workspace
ls -la examples/my_resume/

# Or use the agent command
uv run resume-agent --prompt "/files"
```

### "Config file not found"
The agent will use defaults. Just make sure your resume is in the workspace.

### "Command blocked for safety"
Some bash commands are blocked. Use only safe commands like `ls`, `cat`, `grep`.

### "File too large"
Files must be under 10MB. If your resume is larger, convert it to text first.

---

## 📚 More Information

- **[Getting Started Guide](./getting-started.md)** - Detailed setup guide
- **[Architecture Overview](../.claude/CLAUDE.md)** - Technical details
- **[API Reference](./api-reference/phase1-quick-reference.md)** - API reference for developers

---

## 🎉 Ready to Go!

You're all set! Here's what to do next:

1. **Copy your resume** to the workspace
2. **Start the agent**: `uv run resume-agent --workspace ./examples/my_resume`
3. **Ask it to analyze** your resume
4. **Request improvements** for specific sections
5. **Save the improved version** in your preferred format

Good luck with your resume! 🚀
