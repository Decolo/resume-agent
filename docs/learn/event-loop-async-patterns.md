# Event Loop & Async Patterns: Python vs JavaScript

> 深入理解 Python asyncio 和 JavaScript 事件循环的异步编程模式

## 目录

- [核心概念](#核心概念)
- [Python asyncio 模式](#python-asyncio-模式)
- [JavaScript/Node.js 模式](#javascriptnodejs-模式)
- [实战案例：CLI 用户输入](#实战案例cli-用户输入)
- [常见误区](#常见误区)
- [最佳实践](#最佳实践)

---

## 核心概念

### 什么是事件循环？

事件循环（Event Loop）是异步编程的核心机制，负责：
1. **调度任务**：决定哪个任务该执行
2. **管理 I/O**：处理网络、文件、用户输入等 I/O 操作
3. **协调并发**：让多个任务"看起来"同时运行

### 阻塞 vs 非阻塞

```
┌─────────────────────────────────────────────────┐
│ 同步阻塞 (Synchronous Blocking)                  │
├─────────────────────────────────────────────────┤
│ 线程 1: [等待 I/O ████████████] [继续执行]       │
│ 线程 2: [闲置 ░░░░░░░░░░░░░░░] [执行]           │
│                                                 │
│ 问题：线程 1 被卡住，浪费 CPU 资源                │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ 异步非阻塞 (Asynchronous Non-blocking)           │
├─────────────────────────────────────────────────┤
│ 事件循环: [任务A] [任务B] [任务C] [任务A继续]     │
│           ↓ I/O   ↓ I/O   ↓ I/O   ↑ I/O完成     │
│                                                 │
│ 优势：单线程处理多个任务，高效利用 CPU            │
└─────────────────────────────────────────────────┘
```

---

## Python asyncio 模式

### 1. 基本结构

```python
import asyncio

# 定义异步函数
async def my_async_function():
    print("开始")
    await asyncio.sleep(1)  # 暂停，让出控制权
    print("结束")
    return "完成"

# 运行异步函数
result = asyncio.run(my_async_function())
```

**关键点**：
- `async def` 定义协程函数（coroutine）
- `await` 暂停当前协程，等待异步操作完成
- `asyncio.run()` 创建事件循环并运行协程

### 2. asyncio.run() 的作用

```python
# cli.py 中的入口点
def main():
    # ... 同步代码 ...
    asyncio.run(run_interactive(agent, session_manager))
    #           ↑ 异步函数
```

`asyncio.run()` 做了什么：
1. **创建事件循环**：`loop = asyncio.new_event_loop()`
2. **运行协程**：`loop.run_until_complete(coroutine)`
3. **清理资源**：关闭事件循环，清理未完成的任务

**等价于**：
```python
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
try:
    loop.run_until_complete(run_interactive(agent, session_manager))
finally:
    loop.close()
```

### 3. 并发执行多个任务

```python
async def task1():
    print("任务1 开始")
    await asyncio.sleep(2)
    print("任务1 完成")

async def task2():
    print("任务2 开始")
    await asyncio.sleep(1)
    print("任务2 完成")

# 并发运行
async def main():
    await asyncio.gather(task1(), task2())
    # 输出顺序：
    # 任务1 开始
    # 任务2 开始
    # 任务2 完成  (1秒后)
    # 任务1 完成  (2秒后)

asyncio.run(main())
```

---

## JavaScript/Node.js 模式

### 1. 基本结构

```javascript
// 定义异步函数
async function myAsyncFunction() {
    console.log("开始");
    await sleep(1000);  // 暂停 1 秒
    console.log("结束");
    return "完成";
}

// 运行异步函数
// 方式 1: Top-level await (ES2022+)
const result = await myAsyncFunction();

// 方式 2: IIFE (传统方式)
(async () => {
    const result = await myAsyncFunction();
})();
```

**关键点**：
- JavaScript 的事件循环是**内置的**，不需要手动创建
- `async/await` 语法与 Python 几乎相同
- Node.js 启动时自动初始化事件循环

### 2. Promise 与 async/await

```javascript
// Promise 链式调用
fetch('https://api.example.com/data')
    .then(response => response.json())
    .then(data => console.log(data))
    .catch(error => console.error(error));

// async/await 等价写法（更清晰）
async function fetchData() {
    try {
        const response = await fetch('https://api.example.com/data');
        const data = await response.json();
        console.log(data);
    } catch (error) {
        console.error(error);
    }
}
```

### 3. 并发执行多个任务

```javascript
async function task1() {
    console.log("任务1 开始");
    await sleep(2000);
    console.log("任务1 完成");
}

async function task2() {
    console.log("任务2 开始");
    await sleep(1000);
    console.log("任务2 完成");
}

// 并发运行
await Promise.all([task1(), task2()]);
// 输出顺序与 Python 相同
```

---

## 实战案例：CLI 用户输入

### 问题：如何在异步环境中获取用户输入？

在 `resume_agent/cli.py` 的 `run_interactive()` 函数中：

```python
async def run_interactive(agent, session_manager):
    """交互式聊天循环"""
    session = PromptSession(history=FileHistory(str(history_file)))

    while True:
        # 获取用户输入
        user_input = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: session.prompt(prompt_prefix),
        )

        # 处理输入
        response = await agent.run(user_input)
        console.print(response)
```

### 为什么需要 run_in_executor？

**问题**：`session.prompt()` 是**同步阻塞**函数
- 调用时会卡住整个线程，等待用户输入
- 如果直接在 `async def` 中调用，会阻塞事件循环
- 其他异步任务无法运行

**解决方案**：`run_in_executor` 把阻塞操作放到线程池执行

```python
# 错误示例 ❌
async def run_interactive():
    user_input = session.prompt("You: ")  # 阻塞整个事件循环！

# 正确示例 ✅
async def run_interactive():
    user_input = await asyncio.get_event_loop().run_in_executor(
        None,  # 使用默认 ThreadPoolExecutor
        lambda: session.prompt("You: ")  # 在线程池中执行
    )
```

### 执行流程图

```
┌─────────────────────────────────────────────────────────┐
│ 主线程 (事件循环)                                         │
├─────────────────────────────────────────────────────────┤
│ 1. 遇到 await run_in_executor                            │
│    ↓                                                    │
│ 2. 把 session.prompt() 提交到线程池                      │
│    ↓                                                    │
│ 3. 暂停当前协程，释放控制权                               │
│    ↓                                                    │
│ 4. 事件循环可以处理其他任务 ✅                            │
│    ↓                                                    │
│ 5. 线程池返回结果后，恢复协程                             │
│    ↓                                                    │
│ 6. user_input 获得值，继续执行                           │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ 线程池 (后台线程)                                         │
├─────────────────────────────────────────────────────────┤
│ 1. 执行 session.prompt("You: ")                         │
│    ↓                                                    │
│ 2. 阻塞等待用户输入 ⏳                                    │
│    ↓                                                    │
│ 3. 用户按回车                                            │
│    ↓                                                    │
│ 4. 返回输入内容给主线程                                   │
└─────────────────────────────────────────────────────────┘
```

### JavaScript 对比

Node.js 的 `readline` 本身就是异步的，不需要特殊处理：

```javascript
import readline from 'readline';
import { promisify } from 'util';

const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

// 方式 1: 原生 callback
rl.question("You: ", (answer) => {
    console.log("输入:", answer);
});

// 方式 2: promisify 后使用 await
const question = promisify(rl.question).bind(rl);

async function runInteractive() {
    while (true) {
        const userInput = await question("You: ");  // 直接 await
        const response = await agent.run(userInput);
        console.log(response);
    }
}
```

**关键差异**：
- **Python**: `session.prompt()` 是同步阻塞 → 需要 `run_in_executor`
- **Node.js**: `readline.question()` 是异步非阻塞 → 直接 `await`

---

## 常见误区

### 误区 1：await 会阻塞整个程序

❌ **错误理解**：
```python
async def main():
    result = await long_task()  # 整个程序被阻塞？
    print(result)
```

✅ **正确理解**：
- `await` 只暂停**当前协程**
- 事件循环可以运行**其他协程**
- 只有当前函数的后续代码会等待

```python
async def task1():
    print("任务1 开始")
    await asyncio.sleep(5)  # 暂停 5 秒
    print("任务1 完成")

async def task2():
    for i in range(5):
        print(f"任务2 运行中 {i}")
        await asyncio.sleep(1)

# 并发运行
await asyncio.gather(task1(), task2())
# 输出：
# 任务1 开始
# 任务2 运行中 0
# 任务2 运行中 1
# 任务2 运行中 2
# 任务2 运行中 3
# 任务2 运行中 4
# 任务1 完成
```

### 误区 2：async 函数自动并发

❌ **错误理解**：
```python
async def main():
    await task1()  # 等待完成
    await task2()  # 再等待完成
    # 这是串行执行，不是并发！
```

✅ **正确写法**：
```python
async def main():
    # 方式 1: asyncio.gather
    await asyncio.gather(task1(), task2())

    # 方式 2: asyncio.create_task
    t1 = asyncio.create_task(task1())
    t2 = asyncio.create_task(task2())
    await t1
    await t2
```

### 误区 3：Python 的 / 可以拼接字符串

❌ **错误**：
```python
path = "home" / "user" / "file.txt"  # TypeError!
```

✅ **正确**：
```python
# 方式 1: Path 对象（推荐）
from pathlib import Path
path = Path("home") / "user" / "file.txt"

# 方式 2: os.path.join
import os
path = os.path.join("home", "user", "file.txt")

# 方式 3: 字符串拼接
path = "home" + "/" + "user" + "/" + "file.txt"
```

**原理**：`Path` 类重载了 `/` 运算符（`__truediv__` 方法），普通字符串没有。

---

## 最佳实践

### 1. 选择合适的并发模式

```python
# ✅ I/O 密集型任务 → asyncio
async def fetch_data():
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

# ✅ CPU 密集型任务 → multiprocessing
from multiprocessing import Pool
def compute_heavy_task(data):
    return sum(i**2 for i in range(data))

with Pool() as pool:
    results = pool.map(compute_heavy_task, [1000000, 2000000])
```

### 2. 避免在 async 中调用阻塞函数

```python
# ❌ 错误：直接调用阻塞函数
async def bad_example():
    data = requests.get(url).json()  # 阻塞！

# ✅ 正确：使用异步库
async def good_example():
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()

# ✅ 或者：用 run_in_executor 包装
async def alternative():
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(
        None,
        lambda: requests.get(url).json()
    )
```

### 3. 正确处理异常

```python
async def safe_task():
    try:
        result = await risky_operation()
        return result
    except Exception as e:
        logger.error(f"任务失败: {e}")
        return None

# 并发任务的异常处理
async def main():
    results = await asyncio.gather(
        task1(),
        task2(),
        task3(),
        return_exceptions=True  # 不让一个任务的异常影响其他任务
    )

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"任务 {i} 失败: {result}")
```

### 4. 使用 asyncio.create_task 提前启动任务

```python
# ❌ 低效：串行执行
async def slow():
    data1 = await fetch_data1()  # 等待 2 秒
    data2 = await fetch_data2()  # 再等待 2 秒
    # 总共 4 秒

# ✅ 高效：并发执行
async def fast():
    task1 = asyncio.create_task(fetch_data1())  # 立即开始
    task2 = asyncio.create_task(fetch_data2())  # 立即开始
    data1 = await task1  # 等待完成
    data2 = await task2  # 等待完成
    # 总共 2 秒
```

---

## 参考资源

### Python
- [asyncio 官方文档](https://docs.python.org/3/library/asyncio.html)
- [Real Python: Async IO in Python](https://realpython.com/async-io-python/)

### JavaScript
- [MDN: async function](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/async_function)
- [Node.js Event Loop](https://nodejs.org/en/docs/guides/event-loop-timers-and-nexttick/)

### 对比
- [Async Python vs JavaScript](https://www.freecodecamp.org/news/async-await-javascript-python/)

---

## 总结

| 特性 | Python asyncio | JavaScript/Node.js |
|------|----------------|-------------------|
| 事件循环初始化 | 手动 `asyncio.run()` | 自动内置 |
| 异步函数定义 | `async def` | `async function` |
| 等待异步操作 | `await` | `await` |
| 并发执行 | `asyncio.gather()` | `Promise.all()` |
| 阻塞函数处理 | `run_in_executor()` | 大多数 API 原生异步 |
| 适用场景 | I/O 密集型 | I/O 密集型 |

**核心思想**：
- `await` 暂停当前函数，不阻塞事件循环
- 事件循环在等待 I/O 时可以运行其他任务
- 阻塞操作必须放到线程池或使用异步 API

---

*文档版本: 1.0*
*最后更新: 2026-02-09*
