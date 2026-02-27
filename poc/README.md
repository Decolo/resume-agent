# LinkedIn Browser Control POC

Quick proof-of-concept for controlling a logged-in Chrome browser to post content to LinkedIn via Chrome DevTools Protocol (CDP).

## Why This Approach?

- **No OAuth needed**: Uses your existing logged-in Chrome session
- **No API limits**: Bypasses LinkedIn API restrictions
- **Simple**: Just connect to Chrome and automate the UI

## Prerequisites

### Python Version

```bash
# Install Playwright
pip install playwright
playwright install chromium
```

### TypeScript Version (Optional)

```bash
# Install Puppeteer
npm install puppeteer-core
```

### Vercel Agent Browser (AI-Powered)

```bash
# Install globally
npm install -g agent-browser
agent-browser install
```

## Usage

### 1. Launch Chrome with Remote Debugging

```bash
# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222

# Linux
google-chrome --remote-debugging-port=9222

# Windows
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

**Important**: Log into LinkedIn in this Chrome instance before running the script.

### 2. Test the Connection (Optional)

```bash
python poc/test_connection.py
```

This verifies that Chrome is accessible via CDP before running the LinkedIn POC.

### 3. Run the POC Script

#### Python

```bash
python poc/linkedin_browser_poc.py "Your post content here"
```

#### TypeScript (Puppeteer)

```bash
npx ts-node poc/linkedin_browser_poc.ts
```

#### Vercel Agent Browser (AI-Powered)

```bash
node poc/linkedin_vercel_agent.js "Your post content"
```

**Advantage**: Uses natural language instructions instead of hardcoded selectors. More resilient to LinkedIn UI changes.

## How It Works

1. **Connect**: Script connects to Chrome via CDP on port 9222
2. **Navigate**: Goes to `linkedin.com/feed`
3. **Interact**: Clicks "Start a post", fills content, clicks "Post"
4. **Verify**: Post appears on your LinkedIn feed

## Comparison: Playwright vs Puppeteer vs Vercel Agent Browser

| Feature | Playwright | Puppeteer | Vercel Agent Browser |
|---------|-----------|-----------|---------------------|
| **Installation** | `pip install playwright` | `npm install puppeteer-core` | `npm install -g agent-browser` |
| **Selector Strategy** | Hardcoded CSS/XPath | Hardcoded CSS/XPath | AI-powered natural language |
| **Resilience** | Breaks on UI changes | Breaks on UI changes | Adapts to UI changes |
| **Performance** | Fast | Fast | Slower (LLM overhead) |
| **Dependencies** | Python + Chromium | Node.js only | Node.js + Rust CLI |
| **Best For** | Python projects | Node.js projects | Dynamic UIs, less maintenance |

**Recommendation**:
- Use **Playwright** if you're already in Python (integrates with resume-agent)
- Use **Vercel Agent Browser** if LinkedIn changes their UI frequently
- Use **Puppeteer** for lightweight Node.js projects

## Limitations

- Requires Chrome to be running with debugging port
- Selectors may break if LinkedIn changes their UI
- No error recovery for network issues
- Single post only (no scheduling, media, etc.)

## Next Steps

To integrate this into the resume agent:

1. Add as a tool in `resume_agent/tools/linkedin_tool.py`
2. Create `LinkedInAgent` in `resume_agent/core/agents/`
3. Add configuration for CDP port in `config/config.yaml`
4. Handle edge cases (rate limiting, session expiry, etc.)

## Security Notes

- CDP gives full browser control - only use on trusted networks
- Don't expose port 9222 to the internet
- Consider using Chrome profiles to isolate sessions
