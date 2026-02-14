# Vercel AI SDK - Architecture Analysis

**Date**: 2026-02-03
**Analyzed Version**: Latest (main branch)
**Repository**: https://github.com/vercel/ai

---

## 🎯 Executive Summary

Vercel AI SDK is a **production-grade, provider-agnostic TypeScript toolkit** for building AI agents and applications. It's designed for streaming-first experiences with excellent DX (Developer Experience) and supports all major LLM providers.

### Key Strengths vs. Your Resume Agent

| Feature | Vercel AI SDK | Your Resume Agent | Winner |
|---------|---------------|-------------------|--------|
| **Streaming** | ✅ First-class, built-in | ❌ Not implemented | Vercel |
| **Provider Abstraction** | ✅ 20+ providers | ⚠️ Gemini only | Vercel |
| **TypeScript Types** | ✅ Full type inference | ⚠️ Python (no types) | Vercel |
| **UI Integration** | ✅ React/Vue/Svelte hooks | ❌ CLI only | Vercel |
| **Tool Execution** | ✅ Parallel + streaming | ✅ Parallel (asyncio) | Tie |
| **Multi-Agent** | ⚠️ Basic (ToolLoopAgent) | ✅ Advanced (orchestration) | You |
| **Session Persistence** | ❌ Not built-in | ✅ Full implementation | You |
| **Observability** | ✅ OpenTelemetry | ✅ Custom (AgentObserver) | Tie |
| **Edge Runtime** | ✅ Optimized | ❌ N/A (Python) | Vercel |

---

## 🏗️ Architecture Overview

### Core Abstractions

```typescript
// 1. Provider Abstraction
interface LanguageModel {
  doGenerate(options): Promise<GenerateResult>
  doStream(options): AsyncIterable<StreamPart>
}

// 2. Agent Abstraction
class ToolLoopAgent {
  generate(prompt): Promise<GenerateTextResult>
  stream(prompt): Promise<StreamTextResult>
}

// 3. Tool Abstraction
interface Tool {
  description: string
  parameters: Schema
  execute?: (args) => Promise<result> | AsyncIterable<result>
}
```

### Key Design Patterns

#### 1. **Streaming-First Architecture**

```typescript
// Everything returns streams by default
const result = await streamText({
  model: openai('gpt-5'),
  prompt: 'Hello',
  tools: { weather: weatherTool }
});

// Multiple stream types:
result.textStream      // Raw text chunks
result.fullStream      // Text + tool calls + metadata
result.toTextStreamResponse()  // HTTP Response
```

**Why This Matters:**
- Better UX (progressive rendering)
- Lower perceived latency
- Works on edge runtimes (Vercel Edge, Cloudflare Workers)
- Your agent could benefit from this for long-running tasks

#### 2. **Provider-Agnostic Design**

```typescript
// Unified interface across providers
import { openai } from '@ai-sdk/openai';
import { anthropic } from '@ai-sdk/anthropic';
import { google } from '@ai-sdk/google';

// Same API, different providers
const result1 = await generateText({ model: openai('gpt-5'), ... });
const result2 = await generateText({ model: anthropic('claude-opus-4-5'), ... });
const result3 = await generateText({ model: google('gemini-3-flash'), ... });
```

**Implementation:**
- Each provider implements `LanguageModelV3` interface
- Adapter pattern converts provider-specific formats
- Your `llm.py` could be refactored to support this pattern

#### 3. **Tool Loop Agent Pattern**

```typescript
class ToolLoopAgent {
  async generate({ prompt, tools }) {
    let step = 0;
    const stopCondition = stepCountIs(20); // Max 20 steps

    while (!stopCondition(step)) {
      // 1. Call LLM
      const response = await model.doGenerate({ prompt, tools });

      // 2. If tool calls, execute them
      if (response.toolCalls) {
        const results = await executeToolCalls(response.toolCalls);
        prompt = [...prompt, response, results]; // Add to history
        step++;
        continue;
      }

      // 3. No tool calls, return text
      return response.text;
    }
  }
}
```

**Key Differences from Your Agent:**
- **Stop Conditions**: Configurable (stepCountIs, custom predicates)
- **Callbacks**: `onStepFinish` for observability
- **Simpler**: No multi-agent orchestration (that's a feature you have!)

#### 4. **Parallel Tool Execution**

```typescript
// From execute-tool-call.ts
async function executeToolCalls(toolCalls) {
  // Execute all tools in parallel
  return Promise.all(
    toolCalls.map(call => executeToolCall(call))
  );
}
```

**Same as your implementation!** You use `asyncio.gather()`, they use `Promise.all()`.

#### 5. **Streaming Tool Results**

```typescript
// Tools can stream partial results!
const weatherTool = {
  execute: async function* (args) {
    yield { type: 'preliminary', output: 'Fetching weather...' };
    const data = await fetchWeather(args.city);
    yield { type: 'final', output: data };
  }
};
```

**This is NEW!** Your tools return `ToolResult` synchronously. Streaming tool results would enable:
- Progress updates during long-running operations
- Partial results (e.g., "Found 5 resumes so far...")
- Better UX for slow tools

---

## 🔥 Production Patterns You Should Adopt

### 1. **Retry with Exponential Backoff**

```typescript
// From util/retry-with-exponential-backoff.ts
export async function retryWithExponentialBackoff<T>({
  fn,
  maxRetries = 2,
  initialDelayMs = 2000,
  backoffFactor = 2,
}: {
  fn: () => PromiseLike<T>;
  maxRetries?: number;
  initialDelayMs?: number;
  backoffFactor?: number;
}): Promise<T> {
  let lastError: unknown;
  let delayMs = initialDelayMs;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      if (attempt < maxRetries) {
        await delay(delayMs);
        delayMs *= backoffFactor;
      }
    }
  }

  throw lastError;
}
```

**You have this!** Your `retry.py` is very similar. ✅

### 2. **OpenTelemetry Integration**

```typescript
// From telemetry/record-span.ts
export async function recordSpan<T>({
  name,
  attributes,
  tracer,
  fn,
}: {
  name: string;
  attributes: Record<string, any>;
  tracer: Tracer;
  fn: (span: Span) => Promise<T>;
}): Promise<T> {
  return tracer.startActiveSpan(name, { attributes }, async span => {
    try {
      const result = await fn(span);
      span.setStatus({ code: SpanStatusCode.OK });
      return result;
    } catch (error) {
      span.recordException(error);
      span.setStatus({ code: SpanStatusCode.ERROR });
      throw error;
    } finally {
      span.end();
    }
  });
}
```

**What You're Missing:**
- Distributed tracing (spans, traces)
- Integration with observability platforms (DataDog, New Relic)
- Your `AgentObserver` is good for logging, but not for production monitoring

**Recommendation**: Add OpenTelemetry support to `observability.py`

### 3. **Abort Signal Handling**

```typescript
// Graceful cancellation
const abortController = new AbortController();

const result = streamText({
  model: openai('gpt-5'),
  prompt: 'Long task...',
  abortSignal: abortController.signal,
});

// User cancels
abortController.abort();
```

**You Don't Have This!** Your agent can't be cancelled mid-execution.

**Recommendation**: Add `asyncio.CancelledError` handling and propagate cancellation to tools.

### 4. **Stop Conditions**

```typescript
// From stop-condition.ts
export const stepCountIs = (maxSteps: number): StopCondition =>
  ({ stepCount }) => stepCount >= maxSteps;

export const toolCallCountIs = (maxToolCalls: number): StopCondition =>
  ({ toolCallCount }) => toolCallCount >= maxToolCalls;

// Custom conditions
const stopWhen = ({ text }) => text.includes('DONE');
```

**You Have Basic Version**: `max_steps` parameter

**What's Better Here**: Composable predicates, multiple conditions

**Recommendation**: Refactor to `StopCondition` pattern for flexibility

### 5. **Middleware Pattern**

```typescript
// From middleware/wrap-language-model.ts
export function wrapLanguageModel({
  model,
  middleware,
}: {
  model: LanguageModel;
  middleware: LanguageModelMiddleware;
}): LanguageModel {
  return {
    ...model,
    doGenerate: async (options) => {
      const modifiedOptions = await middleware.transformParams?.(options) ?? options;
      const result = await model.doGenerate(modifiedOptions);
      return await middleware.transformResult?.(result) ?? result;
    },
  };
}

// Usage: Add caching, logging, rate limiting as middleware
const cachedModel = wrapLanguageModel({
  model: openai('gpt-5'),
  middleware: cacheMiddleware,
});
```

**You Don't Have This!** Your caching is hardcoded in `llm.py`.

**Recommendation**: Extract caching, retry, observability into middleware pattern for composability.

---

## 🚀 Streaming Implementation Deep Dive

### How Streaming Works

```typescript
// 1. Model returns async iterable
async function* doStream(options) {
  const response = await fetch(apiUrl, { body: JSON.stringify(options) });
  const reader = response.body.getReader();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    // Parse SSE chunks
    const chunk = parseSSE(value);
    yield { type: 'text-delta', textDelta: chunk.text };

    if (chunk.toolCall) {
      yield { type: 'tool-call', toolCall: chunk.toolCall };
    }
  }
}

// 2. Agent consumes stream
const result = await streamText({ model, prompt, tools });

for await (const part of result.fullStream) {
  if (part.type === 'text-delta') {
    process.stdout.write(part.textDelta);
  } else if (part.type === 'tool-call') {
    const toolResult = await executeTool(part.toolCall);
    // Tool result is automatically added to next LLM call
  }
}
```

### Stream Types

```typescript
// 1. textStream - Just the text
for await (const text of result.textStream) {
  console.log(text); // "Hello", " world", "!"
}

// 2. fullStream - Everything (text + tool calls + metadata)
for await (const part of result.fullStream) {
  switch (part.type) {
    case 'text-delta': console.log(part.textDelta); break;
    case 'tool-call': console.log('Tool:', part.toolCall); break;
    case 'tool-result': console.log('Result:', part.toolResult); break;
    case 'finish': console.log('Done:', part.finishReason); break;
  }
}

// 3. toTextStreamResponse() - HTTP Response for web apps
return result.toTextStreamResponse();
```

### Why This Matters for Your Agent

**Current State**: Your agent blocks until entire response is ready

```python
# Your current implementation
async def run(self, user_input: str) -> str:
    # ... tool loop ...
    return final_text  # Returns after everything is done
```

**With Streaming**:

```python
async def run_stream(self, user_input: str) -> AsyncIterator[str]:
    # ... tool loop ...
    async for chunk in llm_response:
        if chunk.type == 'text':
            yield chunk.text  # Stream text as it arrives
        elif chunk.type == 'tool_call':
            result = await execute_tool(chunk.tool_call)
            # Continue streaming after tool execution
```

**Benefits**:
- User sees progress immediately
- Better for long resume analysis tasks
- Can cancel mid-execution
- Lower perceived latency

---

## 🎨 UI Integration Patterns

### React Hook Example

```typescript
// From packages/react/src/use-completion.ts
export function useCompletion({
  api = '/api/completion',
  onFinish,
  onError,
}: {
  api?: string;
  onFinish?: (text: string) => void;
  onError?: (error: Error) => void;
}) {
  const [completion, setCompletion] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const complete = async (prompt: string) => {
    setIsLoading(true);

    const response = await fetch(api, {
      method: 'POST',
      body: JSON.stringify({ prompt }),
    });

    const reader = response.body.getReader();
    let text = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = new TextDecoder().decode(value);
      text += chunk;
      setCompletion(text); // Update UI progressively
    }

    setIsLoading(false);
    onFinish?.(text);
  };

  return { completion, complete, isLoading };
}

// Usage in React component
function ChatUI() {
  const { completion, complete, isLoading } = useCompletion({
    api: '/api/chat',
  });

  return (
    <div>
      <button onClick={() => complete('Improve my resume')}>
        Send
      </button>
      <div>{completion}</div> {/* Updates in real-time */}
      {isLoading && <Spinner />}
    </div>
  );
}
```

**Why This Matters**: If you ever want to build a web UI for your resume agent, this pattern is essential.

---

## 📊 Comparison: Tool Execution

### Vercel AI SDK

```typescript
// Parallel execution with streaming support
async function executeToolCall({ toolCall, tools }) {
  const tool = tools[toolCall.name];

  // Tool can be sync or async generator
  const stream = executeTool({
    execute: tool.execute,
    input: toolCall.args,
  });

  let output;
  for await (const part of stream) {
    if (part.type === 'preliminary') {
      // Partial result (streaming)
      onPreliminaryResult(part.output);
    } else {
      output = part.output;
    }
  }

  return { type: 'tool-result', output };
}
```

### Your Resume Agent

```python
# From llm.py
async def execute_single_tool(fc):
    tool_name = fc.name
    tool_func = self.tools[tool_name]

    # Execute tool (sync or async)
    if asyncio.iscoroutinefunction(tool_func):
        result = await tool_func(**args)
    else:
        result = tool_func(**args)

    return types.Part.from_function_response(
        name=tool_name,
        response={"result": result.output}
    )

# Parallel execution
function_responses = await asyncio.gather(
    *[execute_single_tool(fc) for fc in function_calls],
    return_exceptions=False
)
```

**Key Differences**:
1. **Streaming**: Vercel supports streaming tool results, you don't
2. **Error Handling**: Vercel returns `tool-error` type, you raise exceptions
3. **Preliminary Results**: Vercel can show progress, you return final result only

**Recommendation**: Add streaming tool support for long-running operations (e.g., parsing large PDFs)

---

## 🎯 Key Takeaways & Recommendations

### What Vercel AI SDK Does Better

1. **Streaming-First**: Everything streams by default
   - **Action**: Add `run_stream()` method to your agent
   - **Benefit**: Better UX, lower latency, cancellable operations

2. **Provider Abstraction**: 20+ providers with unified API
   - **Action**: Create `BaseLLMProvider` interface
   - **Benefit**: Easy to switch providers, test with different models

3. **UI Integration**: React/Vue/Svelte hooks
   - **Action**: Build web UI with streaming support
   - **Benefit**: Better than CLI for end users

4. **OpenTelemetry**: Production-grade observability
   - **Action**: Add OpenTelemetry to `observability.py`
   - **Benefit**: Integration with DataDog, New Relic, etc.

5. **Middleware Pattern**: Composable transformations
   - **Action**: Refactor caching/retry as middleware
   - **Benefit**: Cleaner code, easier to extend

### What You Do Better

1. **Multi-Agent Orchestration**: Specialized agents with delegation
   - Vercel only has basic `ToolLoopAgent`
   - Your orchestrator, parser, writer, formatter pattern is more sophisticated

2. **Session Persistence**: Full conversation save/load
   - Vercel doesn't have this built-in
   - Your session management is production-ready

3. **History Management**: Automatic pruning with pair preservation
   - Vercel doesn't handle history overflow
   - Your `HistoryManager` is more robust

### Immediate Action Items

**Priority 1: Streaming (High Impact)**
```python
# Add to llm.py
async def run_stream(self, user_input: str) -> AsyncIterator[str]:
    """Stream responses as they arrive."""
    # Implementation similar to Vercel's streamText
```

**Priority 2: Abort Signal (Medium Impact)**
```python
# Add to agent.py
async def run(self, user_input: str, cancel_token: asyncio.Event = None):
    """Support cancellation mid-execution."""
    if cancel_token and cancel_token.is_set():
        raise asyncio.CancelledError()
```

**Priority 3: Stop Conditions (Low Impact)**
```python
# Add to agent.py
StopCondition = Callable[[Dict], bool]

def step_count_is(max_steps: int) -> StopCondition:
    return lambda state: state['step'] >= max_steps
```

**Priority 4: OpenTelemetry (Medium Impact)**
```python
# Add to observability.py
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("agent.run") as span:
    span.set_attribute("user_input", user_input)
    result = await self.run(user_input)
    span.set_attribute("result_length", len(result))
```

---

## 📚 Further Reading

- **Vercel AI SDK Docs**: https://ai-sdk.dev/docs
- **OpenTelemetry Python**: https://opentelemetry.io/docs/languages/python/
- **Streaming in Python**: https://docs.python.org/3/library/asyncio-stream.html
- **AsyncIterator Pattern**: https://peps.python.org/pep-0525/

---

## 🎓 Lessons Learned

1. **Streaming is Essential**: Modern AI apps need streaming for good UX
2. **Provider Abstraction Pays Off**: Don't lock into one provider
3. **Middleware > Hardcoding**: Composable transformations are more flexible
4. **OpenTelemetry is Standard**: Production apps need distributed tracing
5. **TypeScript Types Help**: Full type inference catches bugs early
6. **Edge Runtime Matters**: Vercel optimizes for serverless/edge deployment

Your resume agent has a **solid foundation** and some **advanced features** (multi-agent, session persistence) that Vercel doesn't have. Adding streaming and better observability would make it production-ready for SaaS deployment.

---

**Next Steps**: Should we analyze LangChain next, or start implementing streaming in your agent?
