# Gemini API Troubleshooting Guide

## Issues Found

### 1. ✅ SOCKS Proxy Support (FIXED)
**Error**: `Using SOCKS proxy, but the 'socksio' package is not installed`

**Solution**: Installed `httpx[socks]`
```bash
uv pip install 'httpx[socks]'
```

### 2. ❌ Location Restriction (CURRENT ISSUE)
**Error**: `400 FAILED_PRECONDITION - User location is not supported for the API use`

**Possible Causes**:
- Gemini API is not available in your region
- Proxy is routing through a restricted region
- API key has location restrictions

**Solutions**:

#### Option A: Check API Key Settings
1. Go to https://aistudio.google.com/apikeys
2. Check if your API key has location restrictions
3. Try creating a new API key

#### Option B: Try Different Proxy Settings
Your current proxy settings:
```bash
https_proxy=http://127.0.0.1:7890
http_proxy=http://127.0.0.1:7890
all_proxy=socks5://127.0.0.1:7890
```

Try temporarily disabling the proxy:
```bash
unset https_proxy
unset http_proxy
unset all_proxy
uv run python test_gemini_api.py
```

#### Option C: Use a Different LLM Provider
Since Gemini is not accessible, consider using:

**OpenAI** (if you have access):
```yaml
# config/config.yaml
api_key: "${OPENAI_API_KEY}"
model: "gpt-4o-mini"  # or gpt-4o
```

**DeepSeek** (cheaper alternative):
```yaml
# config/config.yaml
api_key: "${DEEPSEEK_API_KEY}"
api_base: "https://api.deepseek.com/v1"
model: "deepseek-chat"
```

**Note**: The current codebase uses Google GenAI SDK, which only works with Gemini. To use other providers, you would need to modify `resume_agent/llm.py` to use OpenAI-compatible APIs.

### 3. ❌ Quota Exhausted
**Error**: `429 RESOURCE_EXHAUSTED - You exceeded your current quota`

**Details**:
- Free tier quota: 0 requests remaining
- Model: gemini-2.0-flash-exp

**Solutions**:
1. Wait for quota to reset (usually 24 hours)
2. Upgrade to paid tier at https://ai.google.dev/pricing
3. Use a different API key

## Recommended Next Steps

1. **Check your location and API key restrictions**
   - Visit https://aistudio.google.com/apikeys
   - Check if Gemini API is available in your region

2. **Test without proxy**
   ```bash
   unset https_proxy http_proxy all_proxy
   uv run python test_gemini_api.py
   ```

3. **Consider alternative LLM providers**
   - OpenAI (gpt-4o-mini is cheap and fast)
   - DeepSeek (very cheap, good quality)
   - Claude (via Anthropic API)

4. **If you want to use OpenAI/DeepSeek**, we need to modify the codebase:
   - Current: Uses Google GenAI SDK (Gemini-only)
   - Needed: OpenAI-compatible client (works with OpenAI, DeepSeek, etc.)

## Test Results

```
✓ SOCKS proxy support installed
✓ Client initialized successfully
✗ Location restriction error
✗ Quota exhausted (free tier at 0)
```

## Questions for You

1. Do you have access to OpenAI API or DeepSeek API?
2. Would you like me to modify the codebase to support OpenAI-compatible APIs?
3. Can you check if Gemini API is available in your region?
