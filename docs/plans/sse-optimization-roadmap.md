# SSE 优化路线图

> 当前 SSE 实现的未来优化计划。当前实现对于早期阶段完全够用，本文档记录何时以及如何进行优化。

## 当前状态

**实现位置**：`apps/api/resume_agent_api/api/v1/endpoints/runs.py:106-151`

**当前架构**：
- Polling 模式：每 50ms 轮询一次 `store.snapshot_events()`
- 每个 SSE 连接 = 1 个协程
- InMemory store with global `asyncio.Lock()`
- 支持 `Last-Event-ID` 断线恢复

**适用规模**：< 500 并发 SSE 连接

## 立即实施（低成本高收益）

### 1. 添加 Keepalive 注释

**触发条件**：生产环境部署前

**问题**：长时间无事件时，Nginx/CDN 可能超时断开连接。

**实现**（`runs.py:123-140`）：
```python
async def event_stream() -> AsyncGenerator[str, None]:
    cursor = start_index
    last_keepalive = time.time()

    while True:
        events, run_status = await store.snapshot_events(...)

        if cursor < len(events):
            for event in events[cursor:]:
                yield format_sse_event(event)
                cursor += 1
            last_keepalive = time.time()

        if run_status in TERMINAL_RUN_STATES and cursor >= len(events):
            break

        # 15 秒无数据则发送 keepalive
        if time.time() - last_keepalive > 15:
            yield ": keepalive\n\n"
            last_keepalive = time.time()

        await asyncio.sleep(0.05)
```

**工作量**：10 分钟
**收益**：防止代理超时

### 2. 添加 X-Accel-Buffering Header

**触发条件**：使用 Nginx 部署时

**实现**（`runs.py:141-145`）：
```python
return StreamingResponse(
    event_stream(),
    media_type="text/event-stream",
    headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # ← 添加
    },
)
```

**工作量**：1 分钟
**收益**：确保 Nginx 不缓冲响应

## 中期优化（中等成本）

### 3. SSE 连接数限制

**触发条件**：
- 公开服务部署
- 或观察到单租户打开过多 SSE 连接

**问题**：单租户可以打开无限 SSE 连接，耗尽服务器资源。

**实现**：

**Step 1 — Store 添加连接计数**（`store.py`）：
```python
class InMemoryRuntimeStore:
    def __init__(self, ...):
        # ...
        self._active_sse_connections: Dict[str, int] = defaultdict(int)
        self._max_sse_per_tenant = int(os.getenv("MAX_SSE_PER_TENANT", "50"))

    async def can_open_sse_stream(self, tenant_id: str) -> bool:
        async with self._lock:
            return self._active_sse_connections[tenant_id] < self._max_sse_per_tenant

    async def increment_sse_count(self, tenant_id: str):
        async with self._lock:
            self._active_sse_connections[tenant_id] += 1

    async def decrement_sse_count(self, tenant_id: str):
        async with self._lock:
            count = self._active_sse_connections[tenant_id]
            if count > 0:
                self._active_sse_connections[tenant_id] = count - 1
```

**Step 2 — Endpoint 检查限制**（`runs.py`）：
```python
@router.get("/runs/{run_id}/stream")
async def stream_run_events(...):
    # 检查连接数
    if not await store.can_open_sse_stream(tenant_id):
        raise HTTPException(
            status_code=429,
            detail="Too many concurrent SSE connections for this tenant"
        )

    await store.get_run(...)  # 原有验证
    start_index = await store.event_index_after(...)

    async def event_stream():
        try:
            await store.increment_sse_count(tenant_id)
            # ... 原有 event_stream 逻辑
        finally:
            await store.decrement_sse_count(tenant_id)

    return StreamingResponse(...)
```

**工作量**：1-2 小时
**收益**：防止资源耗尽攻击

### 4. 减少锁竞争

**触发条件**：
- 并发 SSE 连接 > 200
- 或观察到 `snapshot_events()` 成为瓶颈

**问题**：`snapshot_events()` 每次获取两次锁（`get_run` + 拷贝 events）。

**实现**（`store.py:691-700`）：
```python
async def snapshot_events(
    self,
    session_id: str,
    run_id: str,
    tenant_id: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    """Get events snapshot with single lock acquisition."""
    async with self._lock:
        # 直接访问，避免 get_run 的二次锁获取
        session = self._sessions.get(session_id)
        if not session:
            raise APIError(404, "SESSION_NOT_FOUND", f"Session {session_id} not found")

        run = session.runs.get(run_id)
        if not run:
            raise APIError(404, "RUN_NOT_FOUND", f"Run {run_id} not found")

        # Tenant 验证
        if tenant_id and session.tenant_id != tenant_id:
            raise APIError(403, "FORBIDDEN", "Access denied")

        # 返回拷贝，避免外部修改
        return list(run.events), run.status
```

**工作量**：30 分钟
**收益**：减少 50% 锁获取次数，提升 5-10% 吞吐量

## 长期优化（高成本）

### 5. Polling → Push（asyncio.Event）

**触发条件**：
- 并发 SSE 连接 > 1000
- 或 CPU 使用率持续 > 70%（主要来自 polling）

**问题**：Polling 模式下，1000 连接 × 20 次/秒 = 20,000 次 store 查询/秒。

**架构变更**：

```
当前（Polling）:
  协程 A: while True: poll store → sleep(0.05)
  协程 B: while True: poll store → sleep(0.05)
  协程 C: while True: poll store → sleep(0.05)

优化后（Push）:
  协程 A: await event.wait() → 收到通知 → 读取事件
  协程 B: await event.wait() → 收到通知 → 读取事件
  协程 C: await event.wait() → 收到通知 → 读取事件

  Store: 新事件产生 → event.set() → 唤醒所有等待的协程
```

**实现**：

**Step 1 — Store 添加事件通知**（`store.py`）：
```python
class RunRecord:
    # ...
    new_event_signal: asyncio.Event = field(default_factory=asyncio.Event)

class InMemoryRuntimeStore:
    async def append_event(self, session_id: str, run_id: str, event: dict):
        """添加事件并通知等待的 SSE 连接"""
        async with self._lock:
            run = self._get_run_unsafe(session_id, run_id)
            run.events.append(event)
            run.new_event_signal.set()  # 唤醒等待的协程
            run.new_event_signal.clear()  # 重置信号

    async def wait_for_new_events(
        self,
        session_id: str,
        run_id: str,
        timeout: float = 30.0
    ) -> bool:
        """等待新事件或超时"""
        run = await self.get_run(session_id, run_id)
        try:
            await asyncio.wait_for(run.new_event_signal.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
```

**Step 2 — Endpoint 使用 Push**（`runs.py`）：
```python
async def event_stream() -> AsyncGenerator[str, None]:
    cursor = start_index
    last_keepalive = time.time()

    while True:
        events, run_status = await store.snapshot_events(...)

        if cursor < len(events):
            for event in events[cursor:]:
                yield format_sse_event(event)
                cursor += 1
            last_keepalive = time.time()

        if run_status in TERMINAL_RUN_STATES and cursor >= len(events):
            break

        # Keepalive 检查
        if time.time() - last_keepalive > 15:
            yield ": keepalive\n\n"
            last_keepalive = time.time()

        # Push 模式：等待新事件通知（15 秒超时用于 keepalive）
        await store.wait_for_new_events(session_id, run_id, timeout=15.0)
```

**工作量**：1-2 天（需要全面测试）
**收益**：
- 空闲连接零 CPU 消耗
- 支持 10,000+ 并发连接
- 新事件延迟降低到 < 10ms（vs 当前平均 25ms）

**风险**：
- 惊群效应（1000 个协程同时被唤醒）
- 需要仔细处理 Event 的 set/clear 时机
- 增加代码复杂度

**缓解措施**：
- 分批唤醒 + 随机抖动
- 充分的单元测试和压力测试

### 6. 水平扩展（Redis Pub/Sub）

**触发条件**：
- 单机无法支撑负载（CPU/内存/网络瓶颈）
- 需要高可用（多实例部署）

**架构变更**：

```
                    ┌─────────────┐
                    │Load Balancer│
                    │  (sticky)   │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
         ┌────┴────┐ ┌────┴────┐ ┌────┴────┐
         │Server 1 │ │Server 2 │ │Server 3 │
         │SSE conns│ │SSE conns│ │SSE conns│
         └────┬────┘ └────┬────┘ └────┬────┘
              │            │            │
              └────────────┼────────────┘
                           │
                    ┌──────┴──────┐
                    │Redis Pub/Sub│
                    │(事件广播)    │
                    └─────────────┘
```

**实现要点**：
1. Store 改为 Redis 或 PostgreSQL（共享状态）
2. 新事件通过 Redis Pub/Sub 广播到所有服务器
3. Load Balancer 使用 sticky sessions（同一 session 的请求路由到同一服务器）
4. 每台服务器订阅 Redis channel，收到事件后唤醒本地 SSE 连接

**工作量**：1-2 周
**收益**：
- 水平扩展到任意规模
- 高可用（单机故障不影响整体服务）

**成本**：
- 需要 Redis 基础设施
- 运维复杂度显著增加
- 网络延迟增加（Redis 往返）

## 性能基准

| 并发连接数 | 当前架构 | + Push | + 水平扩展 |
|-----------|---------|--------|-----------|
| 100 | ✅ 完全够用 | ✅ | ✅ |
| 500 | ✅ 可用 | ✅ | ✅ |
| 1,000 | ⚠️ 接近上限 | ✅ | ✅ |
| 5,000 | ❌ 不可用 | ✅ 可用 | ✅ |
| 10,000+ | ❌ | ⚠️ 接近上限 | ✅ |

## 决策树

```
当前并发 SSE 连接数是多少？
  │
  ├─ < 200 → 无需优化，当前架构足够
  │
  ├─ 200-500 → 考虑：
  │    ├─ 添加 keepalive（必须）
  │    ├─ 添加连接数限制（推荐）
  │    └─ 减少锁竞争（可选）
  │
  ├─ 500-1000 → 必须：
  │    ├─ 上述所有优化
  │    └─ 开始规划 Push 模式迁移
  │
  └─ > 1000 → 必须：
       ├─ 实施 Push 模式
       └─ 评估是否需要水平扩展
```

## 监控指标

实施优化前，建议先添加监控：

```python
# 在 store 中添加
self._metrics = {
    "active_sse_connections": 0,
    "snapshot_events_calls_per_sec": 0,
    "avg_event_latency_ms": 0,
}

# 在 settings endpoint 暴露
@router.get("/metrics")
async def get_metrics(store: InMemoryRuntimeStore = Depends(get_store)):
    return store.get_metrics()
```

关键指标：
- `active_sse_connections`: 当前活跃 SSE 连接数
- `snapshot_events_calls_per_sec`: Store 查询 QPS
- `avg_event_latency_ms`: 事件从产生到推送的平均延迟

## 参考

- 当前实现：`apps/api/resume_agent_api/api/v1/endpoints/runs.py:106-151`
- Store 实现：`apps/api/resume_agent_api/store.py`
- 学习文档：`docs/learn/sse-websocket-streaming.md`
