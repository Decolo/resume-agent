# LinkedIn Browser Control POC

AI-powered browser automation for posting to LinkedIn using Vercel Agent Browser.

## Why This Approach?

- **No OAuth needed**: Uses your existing logged-in Chrome session
- **No API limits**: Bypasses LinkedIn API restrictions
- **AI-powered**: Natural language instructions adapt to UI changes
- **Resilient**: No brittle CSS selectors that break on updates

## Prerequisites

```bash
# Install Vercel Agent Browser globally
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

### 2. Run the POC Script

```bash
node poc/linkedin_vercel_agent.js "Your post content here"
```

## How It Works

1. **Connect**: Agent connects to Chrome via CDP on port 9222
2. **AI Instructions**: Sends natural language commands to the agent:
   - "navigate to linkedin.com/feed"
   - "click the Start a post button"
   - "type [content] in the post editor"
   - "click the Post button"
3. **Adaptive Execution**: AI figures out selectors dynamically
4. **Verify**: Post appears on your LinkedIn feed

## Why Agent Browser Over Traditional Automation?

**Traditional tools (Playwright/Puppeteer):**
```python
await page.click('button[aria-label*="Start a post"]')  # Breaks if LinkedIn changes this
await page.fill('.ql-editor[contenteditable="true"]', content)  # Fragile selector
```

**Agent Browser:**
```javascript
'click the "Start a post" button'  // AI figures out the selector
'type "content" in the post editor'  // Adapts to UI changes
```

The AI layer makes it resilient to LinkedIn's frequent UI updates.

## Limitations

- Requires Chrome to be running with debugging port
- Slower than hardcoded selectors (LLM inference overhead)
- No error recovery for network issues
- Single post only (no scheduling, media, etc.)
- Requires internet connection for AI model

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
