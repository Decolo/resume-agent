# SSE、WebSocket 与 LLM Streaming

> 基于 resume-agent 项目的实际代码，梳理 SSE 协议、WebSocket 对比、LLM streaming 机制。

## 1. LLM Streaming 机制

### 非流式 vs 流式

```
非流式: 请求 → 等待 3-5 秒 → 一次性返回完整响应
流式:   请求 → 立即开始逐 token 返回 → 用户实时看到输出
```

resume-agent 中 `LLMAgent.run()` 默认 `stream=False`（`packages/core/resume_agent_core/llm.py:333`）。

### OpenAI 风格的 Tool Call Streaming

OpenAI 兼容 API（Kimi、DeepSeek 等）返回 SSE 格式的流，tool call 的处理分三步：

**Step 1 — 接收 function_call_start**（包含工具名称）：
```json
{"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_abc","function":{"name":"file_read","arguments":""}}]}}]}
```

**Step 2 — 累积 arguments 字符串片段**：
```json
{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\"file_path\":\"/foo/bar.txt\"}"}}]}}]}
```

**Step 3 — 检测结束，解析完整 JSON**：
```json
{"choices":[{"delta":{},"finish_reason":"tool_calls"}]}
```

代码位置：`packages/providers/resume_agent_providers/openai_compat.py:261-323`。

### Gemini 的差异

Gemini 在每个 chunk 中返回**完整的 function_call**（已经是 dict），不需要累积 JSON 字符串。
代码位置：`packages/providers/resume_agent_providers/gemini.py:89-107`。

## 2. SSE 协议详解

### 协议格式

SSE (Server-Sent Events) 基于 HTTP，使用 `Content-Type: text/event-stream`。

```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

: keepalive 注释（防止连接超时）

event: data-update
id: 1001
data: {"symbol":"AAPL","price":150.25}

retry: 3000

event: system-alert
id: 1002
data: {"level":"warning","message":"High load"}

data: [DONE]
```

### 字段类型

| 字段 | 作用 | 示例 |
|------|------|------|
| `data:` | 消息内容 | `data: {"key":"value"}` |
| `event:` | 事件类型（默认 `message`） | `event: stock-update` |
| `id:` | 消息 ID（用于断线重连恢复） | `id: 1001` |
| `retry:` | 重连延迟（毫秒） | `retry: 3000` |
| `:` | 注释/keepalive | `: heartbeat` |

### 自动重连

SSE 内置断线重连：
1. 连接断开 → 浏览器自动重连
2. 重连时发送 `Last-Event-ID` header
3. 服务端从该 ID 之后继续推送

### 客户端使用

```javascript
const es = new EventSource('/api/events');

es.addEventListener('data-update', (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
});

es.onerror = () => {
  // 浏览器会自动重连，这里可以做 UI 提示
};
```

### 服务端使用（FastAPI）

```python
async def event_generator():
    yield "retry: 3000\n\n"
    event_id = 0
    while True:
        event_id += 1
        data = json.dumps({"value": event_id})
        yield f"event: update\nid: {event_id}\ndata: {data}\n\n"
        await asyncio.sleep(1)

@app.get("/events")
async def sse_endpoint():
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

## 3. SSE 高并发

### 核心问题：每个 SSE 连接 = 一个服务端协程

```
                   FastAPI Server (单线程 asyncio 事件循环)
                   ┌──────────────────────────────────────┐
                   │                                      │
 User A ──SSE────► │  协程 A: while True: poll → yield    │
 User B ──SSE────► │  协程 B: while True: poll → yield    │
 User C ──SSE────► │  协程 C: while True: poll → yield    │
                   │                                      │
                   │  1000 个连接 = 1000 个协程在内存中     │
                   └──────────────────────────────────────┘
```

协程的生命周期 = SSE 连接的生命周期。在 resume-agent 中，协程活到 run 进入终态
（completed / failed / interrupted）才退出（`runs.py:136`）。

### HTTP/2 解决了什么，没解决什么

| 问题 | HTTP/2 解决了吗 |
|------|:---:|
| 浏览器 6 连接/域名限制 | ✅ 多路复用共享 TCP |
| 服务端协程内存/CPU | ❌ 跟协议版本无关 |
| 服务端锁竞争 | ❌ 跟协议版本无关 |

### Polling vs Push

resume-agent 当前使用 polling 模式（`sleep(0.05)` 每 50ms 轮询）。
1000 连接 × 20 次/秒 = 20,000 次 store 查询/秒。

更高效的方案是 push 模式：用 `asyncio.Event` 通知，空闲连接零 CPU 消耗。

### Nginx 配置要点

```nginx
location /api/ {
    proxy_pass http://backend;
    proxy_buffering off;                    # 关闭缓冲
    proxy_set_header X-Accel-Buffering no;  # 关闭 Nginx 缓冲
    proxy_set_header Connection '';
    proxy_http_version 1.1;
    proxy_read_timeout 3600s;               # SSE 长连接超时
}
```

## 4. SSE vs WebSocket

### 对比

| | SSE | WebSocket |
|---|---|---|
| 方向 | 单向（服务器 → 客户端） | 双向 |
| 协议 | 普通 HTTP | 独立协议（HTTP 升级） |
| 数据格式 | 纯文本 (UTF-8) | 文本 + 二进制 |
| 自动重连 | 浏览器内置 | 需要自己实现 |
| 服务端协程 | 1 个/连接 | 1 个/连接 |
| 并发瓶颈 | 与 WebSocket 相同 | 与 SSE 相同 |

### 关键结论

**WebSocket 不能解决 SSE 的并发问题**。两者在服务端都是 1 连接 = 1 协程。

选择依据是通信模式，不是并发能力：

```
单向推送（LLM streaming、通知、进度）→ SSE
双向通信（聊天、协作编辑、游戏）    → WebSocket
```

### 对于 resume-agent

SSE 是正确的选择：
- 场景是单向推送（run 事件推给客户端）
- 客户端操作（interrupt、approve）用普通 HTTP POST
- SSE 自带重连，实现更简单

## 5. 参考

- resume-agent SSE 实现：`apps/api/resume_agent_api/api/v1/endpoints/runs.py:106-151`
- resume-agent LLM streaming：`packages/core/resume_agent_core/llm.py:491-579`
- OpenAI streaming provider：`packages/providers/resume_agent_providers/openai_compat.py:54-74`
- Gemini streaming provider：`packages/providers/resume_agent_providers/gemini.py:60-87`
