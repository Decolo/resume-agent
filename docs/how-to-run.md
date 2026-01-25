# Resume Agent - How to Run

## Problem Solved ✅

The `resume-agent` command wasn't in your PATH. Here are the solutions:

## Solution 1: Using `uv run` (Recommended)

```bash
uv run resume-agent --workspace ./examples/my_resume
```

This is the simplest and most reliable way to run the agent.

## Solution 2: Using the Helper Script

```bash
./run_agent.sh ./examples/my_resume
```

I've created a helper script that makes it even easier.

## Solution 3: Using Python Module

```bash
uv run python -m resume_agent.cli --workspace ./examples/my_resume
```

Direct Python module execution.

## Solution 4: Create an Alias (Optional)

For convenience, add this to your `~/.zshrc`:

```bash
alias resume-agent='uv run resume-agent'
```

Then reload:

```bash
source ~/.zshrc
```

Now you can use:

```bash
resume-agent --workspace ./examples/my_resume
```

## Quick Start

### Step 1: Copy Your Resume

```bash
cp /path/to/your/resume.pdf ./examples/my_resume/resume.pdf
```

Supported formats: `.pdf`, `.docx`, `.md`, `.txt`, `.json`

### Step 2: Start the Agent

```bash
uv run resume-agent --workspace ./examples/my_resume
```

### Step 3: Interact

```
📝 You: Parse my resume from resume.pdf and analyze it

🤖 Assistant: [Analyzes your resume]

📝 You: Improve my work experience with stronger action verbs

🤖 Assistant: [Suggests improvements]

📝 You: Save as improved_resume.md

🤖 Assistant: [Saves the file]

📝 You: /quit
```

## Available Commands During Session

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/files` | List files in workspace |
| `/reset` | Clear conversation history |
| `/config` | Show configuration |
| `/quit` | Exit the agent |

## Example Prompts

### Analysis
- "Parse my resume from resume.pdf and analyze it"
- "Check if my resume is ATS-friendly"
- "What are the strongest parts of my resume?"

### Improvement
- "Improve my work experience with stronger action verbs"
- "Add quantifiable metrics to my achievements"
- "Make my professional summary more compelling"

### Tailoring
- "Tailor my resume for a Senior Engineer position at Google"
- "Customize for a Data Science role"

### Formatting
- "Convert my resume to HTML format"
- "Save as improved_resume.md"

## Workspace Location

All files are saved in: `./examples/my_resume/`

After using the agent, you'll have:
- `resume.pdf` - Your original resume
- `improved_resume.md` - Improved version
- `resume_final.html` - HTML version
- `resume.json` - JSON version
- `resume_tailored.md` - Tailored for specific job

## Phase 1 Features

✅ Automatic retry logic
✅ Parallel execution (2-3x faster)
✅ Smart caching (10x+ faster for repeated ops)
✅ History pruning
✅ Detailed logging with session statistics
✅ Enhanced security

## Troubleshooting

### Command not found
Use `uv run` prefix:
```bash
uv run resume-agent --workspace ./examples/my_resume
```

### No resume files found
Copy your resume first:
```bash
cp /path/to/your/resume.pdf ./examples/my_resume/resume.pdf
```

### Want to make it permanent
Create an alias in `~/.zshrc`:
```bash
alias resume-agent='uv run resume-agent'
source ~/.zshrc
```

## Next Steps

1. Copy your resume to `./examples/my_resume/`
2. Run: `uv run resume-agent --workspace ./examples/my_resume`
3. Start with: "Parse my resume and analyze it"
4. Request improvements
5. Save the improved versions

Good luck! 🚀
