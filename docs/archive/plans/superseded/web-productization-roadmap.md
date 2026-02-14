# Resume Agent 产品与技术架构演进计划

## 近期（已规划）

### 1. 引导式工作流
- 将简历优化固化为阶段性流程：分析现有简历 → 理解目标岗位 → 差距分析 → 针对性改写 → 格式输出
- 降低用户 prompt 门槛

### 2. JD 匹配能力
- 用户提供 JD 链接/文本，agent 自动做简历-JD 匹配度分析
- 针对性调整措辞、突出相关经验

## 中期：Web UI 产品化

### 交付形态
- Web UI，面向通用用户群体（非仅开发者）

### 架构核心思路：抽象 Workspace Provider
- agent + tool 层不变，抽象 workspace 接口
  - `LocalWorkspace` → CLI 模式，操作本地路径
  - `RemoteWorkspace` → Web 模式，操作服务端临时目录（或 S3/GCS）
- CLI 和 Web 共享同一套 agent + tool 逻辑

### 文件交互
- 上传：拖拽上传 PDF/DOCX → 存到 session workspace
- 过程中：前端实时展示文件列表变化
- 下载：用户选择导出文件，支持批量下载

### 实时交互
- SSE 或 WebSocket streaming 输出
- agent 已是 async loop，加 streaming 层即可

### 预览能力（Web 优势）
- 右侧实时预览改写后的简历渲染效果
- 可视化 diff、格式切换

## 并发与扩展策略

### 内存开销评估
- 单个 agent 实例很轻（几 MB）：config + history + tool 注册表 + observability
- 推理全走 Gemini API，本地无模型
- 真正瓶颈：Gemini API 并发/费用 + 临时文件存储

### 扩展路径（按优先级）
1. **初期**：单机 + session 序列化（已有 session.py 基础），空闲超时后序列化到磁盘释放内存
2. **中期**：无状态化 server + Redis session store，水平扩展
3. **持续关注**：API 费用控制，rate limiting + 用量配额

## 远期待探索

- 质量反馈闭环：recruiter 视角评分、ATS 兼容性检查、量化改进点
- 行业模板与知识库：不同行业（SWE、PM、设计、金融）简历最佳实践

## 未解决问题
- Web 框架选型（FastAPI / Next.js / 其他）
- 用户认证与多租户方案
- 文件存储策略（本地临时目录 vs 对象存储）
- 定价模型（API 费用转嫁方式）
