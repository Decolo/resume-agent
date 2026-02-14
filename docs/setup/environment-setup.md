# Environment Setup Guide

## Quick Start

1. **Copy environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Add your API key to `.env`:**
   ```bash
   # Edit .env and add your key
   GEMINI_API_KEY=your_actual_api_key_here
   ```

3. **Run the agent:**
   ```bash
   uv run resume-agent
   ```

## Configuration Files

### `.env` (Secrets - Never Commit)
Contains sensitive API keys and credentials.

```bash
GEMINI_API_KEY=AIzaSy...
```

**Priority:** Environment variables in `.env` take highest priority.

### `config/config.yaml` (Template - Committed)
Default configuration template. Safe to commit to git.

```yaml
api_key: "${GEMINI_API_KEY}"  # References .env
model: "gemini-2.5-flash"
multi_agent:
  enabled: true
  # ...
```

### `config/config.local.yaml` (Local Overrides - Gitignored)
Optional local overrides. Gitignored for safety.

```yaml
# Override any settings from config.yaml
temperature: 0.9
log_level: "DEBUG"
```

## Configuration Priority

1. **Environment variables** (`.env`) - Highest priority
2. **Local config** (`config.local.yaml`) - Overrides template
3. **Template config** (`config.yaml`) - Defaults

## Getting API Keys

### Google Gemini (Recommended)
1. Visit https://aistudio.google.com/app/apikey
2. Create a new API key
3. Add to `.env`: `GEMINI_API_KEY=your_key`

### OpenAI (Alternative)
1. Visit https://platform.openai.com/api-keys
2. Create a new API key
3. Add to `.env`: `OPENAI_API_KEY=your_key`
4. Update `config.local.yaml`:
   ```yaml
   api_key: "${OPENAI_API_KEY}"
   api_base: "https://api.openai.com/v1"
   model: "gpt-4o"
   ```

## Security Best Practices

✅ **DO:**
- Keep `.env` in `.gitignore`
- Use environment variables for secrets
- Commit `.env.example` as a template
- Commit `config.yaml` as a template

❌ **DON'T:**
- Commit `.env` to git
- Hardcode API keys in config files
- Share your `.env` file
- Commit `config.local.yaml`

## Troubleshooting

### "GEMINI_API_KEY not set" Error

**Solution 1:** Check `.env` file exists
```bash
ls -la .env
cat .env  # Should show GEMINI_API_KEY=...
```

**Solution 2:** Verify dotenv is installed
```bash
uv pip list | grep dotenv
# Should show: python-dotenv==1.2.1
```

**Solution 3:** Set environment variable directly
```bash
export GEMINI_API_KEY="your_key"
uv run resume-agent
```

### Config File Not Found

The agent looks for config files in this order:
1. `config/config.local.yaml` (your local config)
2. `config/config.yaml` (template)

If neither exists, copy the template:
```bash
cp config/config.yaml config/config.local.yaml
```
