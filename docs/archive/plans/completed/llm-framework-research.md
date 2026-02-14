# LLM Framework & Agent 方案调研

## 项目概览

| 维度 | Vercel AI SDK | Kimi CLI | Pi-Mono | OpenCode |
|------|--------------|----------|---------|----------|
| 语言 | TypeScript | Python | TypeScript | TypeScript (Bun) |
| Stars | 21.7K | 6.3K | 11.2K | 103K |
| 年龄 | ~2.5 年 | ~4 个月 | ~6 个月 | ~9.5 个月 |
| 许可证 | Apache 2.0 | Apache 2.0 | MIT | MIT |
| 定位 | LLM SDK/框架 | AI 编码 CLI | AI 编码 CLI + SDK | AI 编码 CLI + 桌面端 |

## 1. Vercel AI SDK (`vercel/ai`)

### 核心价值
- 纯 LLM 抽象层，不是 agent 产品。提供 `generateText`/`streamText`/`generateObject` 等原语
- Provider 抽象是同类最佳：`LanguageModelV3` 接口，切换 provider 只需改一行

### Provider 支持
- 24 个官方 provider（OpenAI, Anthropic, Google, Azure, Bedrock, Mistral, xAI, Cohere, Groq 等）
- 31+ 社区 provider（Ollama, OpenRouter, Cloudflare 等）
- `openai-compatible` 适配器覆盖任意兼容 API

### Tool / Function Calling
- Zod schema 定义参数，自动类型推断 + 运行时校验
- 支持 approval flow（human-in-the-loop）、streaming tool input、MCP
- 错误自动回传给 LLM 自修复

### Agent 能力
- `ToolLoopAgent`：单 agent 循环，`prepareStep` 可动态调整每步的 tools/model
- 无内置多 agent 编排，需自行实现
- `stopWhen` 条件控制循环终止

### 适用场景
- 作为底层 SDK 集成到你自己的 agent 架构中
- 不替代你的 agent 逻辑，替代你的 Gemini SDK 调用层

### 关键限制
- TypeScript only，你的项目是 Python
- 偏向 Vercel/Next.js 生态

---

## 2. Kimi CLI (`MoonshotAI/kimi-cli`)

### 核心价值
- Python 实现的 AI 编码 agent，架构与你的项目最接近
- `kosong` 包是独立的 LLM 抽象层，设计精良

### Provider 支持（kosong 层）
- 6 种 provider：Kimi, OpenAI Legacy, OpenAI Responses, Anthropic, Gemini, Vertex AI
- OpenAI Legacy 兼容任意 OpenAI-compatible API（Ollama, vLLM 等）

### Tool 系统
- 两层：kosong 层的 `SimpleToolset`（通用调度）+ kimi-cli 层的 `KimiToolset`（动态加载、MCP、审批）
- 工具定义用 OpenAI JSON Schema 格式，各 provider 自动转换
- 支持并行 tool 执行

### Agent 能力
- 完整 agent loop：步数限制、自动 context 压缩、重试、subagent 委派
- Flow skills：用 Mermaid/D2 图定义决策树工作流
- Wire 协议（JSON-RPC 2.0）分离 agent 核心与 UI

### 适用场景
- 参考其 `kosong` 包的设计来重构你的 LLM 层
- Wire 协议思路可借鉴用于 Web UI 架构

### 关键限制
- Python >= 3.12（你的项目是 3.10+）
- SearchWeb 锁定 Kimi 平台
- 项目很年轻（4 个月），API 不稳定
- 社区以中文为主

---

## 3. Pi-Mono (`badlogic/pi-mono`)

### 核心价值
- 分层架构：`pi-ai`（LLM 抽象）→ `pi-agent`（agent 运行时）→ `pi-coding-agent`（产品）
- `pi-ai` 可独立使用，类似 Vercel AI SDK 但更轻量

### Provider 支持
- 9 个内置 provider：Anthropic, OpenAI (Responses + Completions), Google, Vertex, Azure, Bedrock, Codex
- 支持跨 provider 对话接续（Claude 开始 → GPT 继续）
- OpenAI-compatible 适配覆盖 Ollama/vLLM 等

### Tool 系统
- TypeBox schema 定义参数（编译时类型 + 运行时校验）
- 校验错误自动回传 LLM 重试
- 核心只有 7 个工具，其余通过扩展系统加载

### Agent 能力
- 双循环架构：外层处理 follow-up，内层处理 tool call
- Session 树状存储，支持分支和回滚
- 自动 context 压缩
- 扩展系统：自定义 tools、commands、UI 组件，可通过 npm 分发

### 适用场景
- 参考其分层架构设计
- 扩展系统的设计思路值得借鉴

### 关键限制
- TypeScript/Node.js only
- 单人维护（bus factor = 1）
- 仍在 v0.x，API 不稳定

---

## 4. OpenCode (`anomalyco/opencode`)

### 核心价值
- Client-Server 架构：headless HTTP server + SSE，TUI/IDE/桌面端都是 client
- 基于 Vercel AI SDK 构建 provider 层，继承其全部 provider 支持

### Provider 支持
- 20+ 内置 provider SDK（通过 AI SDK）
- 75+ provider 通过 OpenAI-compatible 适配
- Models.dev 集成，运行时发现可用模型

### Tool 系统
- Zod schema + `Tool.define()` 工厂
- 14 个内置工具 + MCP 支持
- 三级权限：allow/deny/ask，支持通配符，每个 agent 独立权限集

### Agent 能力
- 多 agent：build（主 agent）、plan（只读分析）、explore（快速搜索）、general（子任务）
- Doom loop 检测（同参数连续调用 3 次触发中断）
- 自动 context 压缩、session fork/revert

### 架构亮点
- HTTP server + OpenAPI spec + SSE = 天然支持多端接入
- 这个架构思路对你的 Web UI 产品化最有参考价值

### 关键限制
- 依赖 Bun 运行时（非 Node.js）
- 强耦合 Vercel AI SDK
- 5K+ open issues，维护压力大
- 推自有 "OpenCode Zen" 模型服务，有 vendor lock-in 倾向

---

## 对你的 Resume Agent 的建议

### 最相关的参考方向

1. **LLM 抽象层**：参考 Kimi CLI 的 `kosong` 包设计（Python，与你技术栈一致）
   - 定义统一的 `ChatProvider` 接口
   - 每个 provider 独立实现（Gemini, OpenAI, Anthropic, etc.）
   - 统一 message/tool call/streaming 格式
   - 你现有的 Gemini-specific 代码变成一个 provider 实现

2. **Web 架构**：参考 OpenCode 的 client-server 分离
   - Agent 核心作为 HTTP server 运行
   - CLI 和 Web UI 都是 client
   - SSE 做实时 streaming
   - OpenAPI spec 保证接口规范

3. **Agent 协议**：参考 Kimi CLI 的 Wire 协议
   - JSON-RPC 2.0 分离 agent 逻辑与 UI 渲染
   - 便于后续接入不同前端

### 不建议直接采用的方案

- **Vercel AI SDK / Pi-Mono**：TypeScript，与你的 Python 栈不兼容
- **直接 fork Kimi CLI**：太重，且绑定 Kimi 生态
- **OpenCode 的 Bun 依赖**：非标准运行时，增加部署复杂度

### 推荐路径

```
当前：Gemini SDK 直接调用
  ↓
Phase 1：抽象 LLM Provider 接口（参考 kosong 设计）
  - 定义 ChatProvider protocol
  - 将现有 Gemini 调用封装为 GeminiProvider
  - 新增 OpenAIProvider / AnthropicProvider
  ↓
Phase 2：统一 tool call 格式
  - 现在已有 OpenAI → Gemini 的转换
  - 改为 tool 定义用统一格式，各 provider 自行转换
  ↓
Phase 3：HTTP server 化（为 Web UI 铺路）
  - FastAPI server 暴露 agent API
  - SSE endpoint 做 streaming
  - CLI 改为调用本地 server（或保留直接模式）
```

## 未解决问题
- 是否需要支持 OpenAI-compatible 协议作为通用 fallback？
- Provider 切换是运行时动态的还是配置时固定的？
- 是否考虑用现有 Python LLM 框架（如 LiteLLM）而非自建抽象层？
