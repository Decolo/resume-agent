# Vercel AI SDK Streaming 实现分析

> 基于 Vercel AI SDK 源码，分析其 LLM streaming 的完整数据管道。重点关注：SSE 解析、text/tool_call 分离、终端渲染策略。

## 1. 原始 SSE 数据

OpenAI 兼容 API（包括 Kimi、DeepSeek 等）设置 `stream: true` 后，HTTP 响应格式：

```
HTTP/1.1 200 OK
Content-Type: text/event-stream

data: {"choices":[{"delta":{"role":"assistant","content":""},"index":0}]}

data: {"choices":[{"delta":{"content":"你好"},"index":0}]}

data: {"choices":[{"delta":{"content":"！"},"index":0}]}

data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_abc","type":"function","function":{"name":"file_read","arguments":""}}]},"index":0}]}

data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\"path\":"}}]},"index":0}]}

data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\"/foo.txt\"}"}}]},"index":0}]}

data: {"choices":[{"delta":{},"finish_reason":"tool_calls","index":0}]}

data: [DONE]
```

两种 delta 不会同时出现在一个 chunk 里：
- `delta.content` — 文本内容（给用户看）
- `delta.tool_calls` — 工具调用（给程序处理）

## 2. 六步处理管道

### Step 1-2：字节流 → JSON 对象

`packages/provider-utils/src/parse-json-event-stream.ts`：

```typescript
stream
  .pipeThrough(new TextDecoderStream())       // bytes → string
  .pipeThrough(new EventSourceParserStream()) // SSE 协议解析（去掉 "data: " 前缀）
  .pipeThrough(new TransformStream({
    async transform({ data }, controller) {
      if (data === '[DONE]') return;          // 忽略结束标记
      controller.enqueue(await safeParseJSON({ text: data, schema }));
    },
  }));
```

输入输出：
```
输入: "data: {\"choices\":[{\"delta\":{\"content\":\"你好\"},\"index\":0}]}"
输出: { choices: [{ delta: { content: "你好" }, index: 0 }] }
```

### Step 3：JSON 对象 → SDK 内部事件（text 和 tool_call 在这里分离）

`packages/openai/src/chat/openai-chat-language-model.ts`：

```typescript
transform(chunk, controller) {
  const delta = chunk.value.choices[0].delta;

  // ---- 文本 ----
  if (delta.content != null) {
    controller.enqueue({
      type: 'text-delta',
      delta: delta.content,     // "你好"
    });
  }

  // ---- 工具调用 ----
  if (delta.tool_calls != null) {
    for (const toolCallDelta of delta.tool_calls) {
      if (toolCalls[toolCallDelta.index] == null) {
        controller.enqueue({
          type: 'tool-input-start',
          toolName: toolCallDelta.function.name,  // "file_read"
        });
      }
      if (toolCallDelta.function?.arguments != null) {
        controller.enqueue({
          type: 'tool-input-delta',
          delta: toolCallDelta.function.arguments, // "{\"path\":"
        });
      }
    }
  }
}
```

经过这一步，统一的 SSE 流被拆成不同类型的事件：

```
原始 SSE chunk                              → SDK 内部事件
─────────────────────────────────────────────────────────────
delta.content = "你好"                       → { type: "text-delta", delta: "你好" }
delta.content = "！"                         → { type: "text-delta", delta: "！" }
delta.tool_calls = [{name: "file_read"...}]  → { type: "tool-input-start", toolName: "file_read" }
delta.tool_calls = [{arguments: "{...}"}]    → { type: "tool-input-delta", delta: "{\"path\":" }
finish_reason = "tool_calls"                 → { type: "tool-input-end" }
```

### Step 4：过滤出纯文本流

`packages/ai/src/generate-text/stream-text.ts`：

```typescript
get textStream() {
  return this.fullStream.pipeThrough(
    new TransformStream({
      transform({ part }, controller) {
        if (part.type === 'text-delta') {
          controller.enqueue(part.text);  // 只放行文本
        }
        // tool-input-start, tool-input-delta 等全部丢弃
      },
    }),
  );
}
```

`textStream` 产出纯字符串序列：`"你好"` → `"！"` → `"我是"` → ...

tool_calls 不会出现在 `textStream` 里，但仍然存在于 `fullStream` 中供 SDK 内部处理。

### Step 5：包装为 for-await 可用的流

`packages/ai/src/util/async-iterable-stream.ts`：

```typescript
type AsyncIterableStream<T> = AsyncIterable<T> & ReadableStream<T>;

// 让 ReadableStream 同时支持 for-await-of 和 .pipeThrough()
function createAsyncIterableStream<T>(source: ReadableStream<T>): AsyncIterableStream<T> {
  const stream = source.pipeThrough(new TransformStream());
  stream[Symbol.asyncIterator] = function() {
    const reader = this.getReader();
    return {
      async next() {
        const { done, value } = await reader.read();
        if (done) { reader.releaseLock(); return { done: true, value: undefined }; }
        return { done: false, value };
      },
      async return() { await reader.cancel(); reader.releaseLock(); return { done: true, value: undefined }; },
    };
  };
  return stream;
}
```

### Step 6：终端输出

`examples/ai-functions/src/stream-text/anthropic-chatbot.ts`：

```typescript
process.stdout.write('\nAssistant: ');
for await (const delta of result.textStream) {
  process.stdout.write(delta);  // 逐个写入终端
}
```

没有 Markdown 实时渲染，没有光标操作。就是 `stdout.write`。

## 3. 完整数据流图

```
Kimi/OpenAI API 返回的 SSE:
  data: {"choices":[{"delta":{"content":"你好"}}]}
  data: {"choices":[{"delta":{"content":"！"}}]}
  data: {"choices":[{"delta":{"tool_calls":[{"function":{"name":"file_read"...}}]}}]}
  data: {"choices":[{"delta":{"tool_calls":[{"function":{"arguments":"..."}}]}}]}
  data: [DONE]
      │
      ▼  Step 1-2: SSE 解析（TextDecoder → EventSourceParser → JSON.parse）
  { delta: { content: "你好" } }
  { delta: { content: "！" } }
  { delta: { tool_calls: [...] } }
      │
      ▼  Step 3: 分类为不同事件类型（OpenAI provider TransformStream）
  { type: "text-delta",       delta: "你好" }
  { type: "text-delta",       delta: "！" }
  { type: "tool-input-start", toolName: "file_read" }
  { type: "tool-input-delta", delta: "{\"path\":..." }
      │
      ▼  Step 4: textStream 过滤（只保留 text-delta）
  "你好"
  "！"
      │                    ← tool 事件被丢弃（仍在 fullStream 中）
      ▼  Step 5-6: for-await → stdout.write
  终端输出: 你好！
```

## 4. Smooth Streaming

`packages/ai/src/generate-text/smooth-stream.ts`

LLM 返回的 token 粒度不均匀（有时半个词，有时一大段）。`smoothStream` 是一个 TransformStream，插在管道中间做 re-chunking + 延迟：

```typescript
smoothStream({
  delayInMs: 10,        // 每个 chunk 之间加 10ms 延迟
  chunking: 'word',     // 按 word 边界重新分块
})
```

核心逻辑：

```typescript
let buffer = '';

async transform(chunk, controller) {
  buffer += chunk.text;

  let match;
  while ((match = detectChunk(buffer)) != null) {
    controller.enqueue({ type: 'text-delta', text: match });
    buffer = buffer.slice(match.length);
    await delay(delayInMs);  // 均匀延迟
  }
  // 不完整的内容留在 buffer 里等下一个 chunk
}
```

支持多种分块策略：
- `'word'` — 按空格/标点分词
- `'line'` — 按换行分块
- `RegExp` — 自定义正则
- `Intl.Segmenter` — 国际化分词（中日韩文）

```typescript
// 日语示例
smoothStream({
  chunking: new Intl.Segmenter('ja', { granularity: 'word' }),
  delayInMs: 100,
})
```

## 5. 终端渲染策略

AI SDK 在终端场景下的核心决策：**streaming 时只做最简单的文本输出，不做 Markdown 实时渲染。**

| 场景 | 渲染方式 |
|------|---------|
| 终端/CLI | `stdout.write(delta)` 原始文本 |
| Web 前端 | React 组件（`useChat`）做 Markdown 渲染 |

原因：终端的"就地更新"依赖 ANSI 光标控制，内容快速增长时容易出现叠影。浏览器 DOM 没有这个问题。

## 6. 与 resume-agent 的对比

```
AI SDK:
  HTTP SSE → EventSourceParser → OpenAI Provider TransformStream → textStream filter → stdout.write

resume-agent:
  HTTP SSE → openai python SDK → _iter_stream_deltas() → StreamDelta → on_stream_delta callback
```

逻辑等价，实现语言不同：
- AI SDK 用 TransformStream 管道做过滤
- resume-agent 用 if 判断 `delta.text` / `delta.function_call_start`

## 7. 源码位置

| 模块 | 文件 |
|------|------|
| SSE 解析 | `packages/provider-utils/src/parse-json-event-stream.ts` |
| OpenAI provider（text/tool 分离） | `packages/openai/src/chat/openai-chat-language-model.ts` |
| SSE chunk schema | `packages/openai/src/chat/openai-chat-api.ts` |
| streamText 主入口 | `packages/ai/src/generate-text/stream-text.ts` |
| textStream 过滤 | `packages/ai/src/generate-text/stream-text.ts:2037-2052` |
| AsyncIterableStream | `packages/ai/src/util/async-iterable-stream.ts` |
| Smooth streaming | `packages/ai/src/generate-text/smooth-stream.ts` |
| 终端示例 | `examples/ai-functions/src/stream-text/anthropic-chatbot.ts` |
