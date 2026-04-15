# 云汐 3.0 总设计执行方案

> **文档定位**：yunxi3.0 全项目的实施总纲，明确各模块的实现顺序、测试顺序、里程碑定义。  
> **核心原则**：严格按阶段推进，每阶段必须通过端到端真实测试方可进入下一阶段；代码质量永远优先于实现速度。

---

## 重要待实现：yunxi2.0 人格与主动性资产迁移

Anchor: YUNXI2_PERSONA_INITIATIVE_MIGRATION

> **2026-04-15 状态更新**：P0-A/P0-B/P0-C/P0-D 已完成。Persona / relationship profile、Continuity 持久化与 open_threads、生活事件库迁移、三层主动事件系统、多维主动决策、expression context 和 proactive generation context 已经落地并接入 Runtime。Phase 5 仍不能视为完整完成，下一阻塞项是 P0-E：日常模式真实 LLM 验收矩阵。

> 状态：重要 / 待实现 / P0 阻塞项。Phase 5 不能被视为完整完成，Phase 6 不应继续扩展，直到本项完成真实 LLM 验收。

yunxi3.0 当前已经具备 Runtime、LLM、MCP、Memory、HeartLake、主动 tick 和 daemon 的最小闭环，但人格与主动性仍只是一套偏工程化骨架。yunxi2.0 中已有的人格设定、用户关系档案、生活事件库、三层主动事件系统、表达姿态和连续性 open_threads 必须迁移到 3.0，否则云汐会逐步偏向“高级脚本执行程序”，而不是住在电脑里的女友。

执行依据见：`docs/design/PERSONA_INITIATIVE_MIGRATION_PLAN.md`。

P0 待实现范围：

1. 迁入结构化 persona profile，替代纯硬编码身份 prompt。
2. 迁入 relationship user profile，让“远”的基本档案和表达偏好成为系统级事实。
3. 迁入并清洗 2.0 的 100+ 生活事件库，事件只作为 LLM 生成素材，不作为固定模板输出。
4. 重建三层主动事件系统：内在生活、共同兴趣、混合事件。
5. 增强主动 decider：时间、情绪、presence、资源、预算、open_threads、未回复主动次数共同参与判断。
6. 接入 expression context，让主动消息有关系感、克制感和生活感，而不是定时器通知。
7. 补齐 Continuity 持久化、relationship summary、emotional summary、open_threads、recent topics。
8. 使用本地 Ollama 和至少一种云端模型做真实 LLM 验收。

完成门槛：

1. 云汐能稳定表现为住在电脑里的亲密伴侣，而不是客服、助手或工具调度器。
2. 主动消息必须由真实 LLM 生成，且输入包含 persona、relationship、event、continuity、emotion、perception。
3. 真实测试要验证人格、关系记忆、主动话题、克制 follow-up 和反工具化。

---

## 〇、模型后端策略（本地优先，云端可切换）

云汐是常驻在用户电脑里的数字伴侣，模型后端不能只假设云端 API 可用。项目级模型策略如下：

1. **本地 Ollama 是一等后端**：日常模式必须支持 `--provider ollama`，通过 `OLLAMA_MODEL` 与 `OLLAMA_BASE_URL` 选择本机模型。
2. **云端模型作为可切换后端**：Moonshot / MiniMax / OpenAI 保留，用于更强推理、长上下文或对比验收。
3. **本地启动不能依赖外网**：当使用 Ollama 日常模式时，daemon healthcheck 不应因 HuggingFace、云端 API 或外部网络不可用而失败。
4. **Embedding 也要本地化**：短期允许 `lexical` 离线降级；后续必须接入 Ollama embedding 模型（如本机可用的 embedding model）或本地 SentenceTransformer 缓存。
5. **真实测试分组**：真实 LLM 验收至少分为本地 Ollama 组和云端模型组；任一组可用时，系统应能启动并完成基础对话。

当前已落地：
- `LLMAdapter.from_env("ollama")` 支持本地 Ollama，不要求 API Key。
- Ollama 默认使用原生 `/api/chat`，避免依赖 OpenAI-compatible `/v1/chat/completions`。
- 本地 Ollama 真实集成测试已加入 `tests/integration/test_ollama_llm.py`。
- `--provider ollama` 的 daemon healthcheck 默认使用 `lexical` embedding provider，避免启动时访问 HuggingFace。

---

## 一、项目全局实施路线图

```
Phase 0：基础准则与开发基建（1 天）
  ├─ 制定并固化《代码实现准则》
  ├─ 建立《开发日志》机制
  └─ 初始化 yunxi3.0 目录结构和依赖配置

Phase 1：MCP 基础设施与工具层骨架（2-3 周）
  ├─ core/mcp/client.py           → MCP stdio Client 封装
  ├─ core/mcp/hub.py              → MCPHub（调度 + 安全 + 审计）
  ├─ core/mcp/security.py         → SecurityManager（四级权限）
  ├─ core/mcp/audit_logger.py     → AuditLogger
  ├─ core/tools/desktop/uia_driver.py      → UIA 基础
  ├─ core/tools/desktop/visual_assertion.py → 视觉断言
  └─ core/mcp/servers/desktop_server.py    → 首个 FastMCP Server

Phase 2：执行引擎与对话验证框架（2 周）
  ├─ core/execution/engine.py     → YunxiExecutionEngine（MCP 适配版）
  ├─ core/prompt_builder.py       → YunxiPromptBuilder
  └─ tests/integration/conversation_tester.py → 对话验证框架

Phase 3：记忆系统与终身学习（2 周）
  ├─ domains/memory/skills/       → ExperienceBuffer / PatternMiner / SkillDistiller / SkillLibrary / FailureReplay / ParamFiller
  ├─ 增强 MemoryManager
  ├─ 连接 AuditLogger → ExperienceBuffer
  └─ 对话验证：技能发现与失败回放

Phase 4：情感系统修复与主动性重建（1.5 周）
  ├─ core/cognition/heart_lake/updater.py   → HeartLakeUpdater
  ├─ core/initiative/engine.py    → InitiativeEngine（删除 generate_sync）
  ├─ core/resident/presence.py    → 简化版在场系统
  └─ 对话验证：情感表达 + 主动性触发

Phase 5：日常模式端到端闭环（1.5 周）
  ├─ core/runtime.py              → YunxiRuntime 统筹层
  ├─ apps/daemon/main.py          → 适配 MCP Hub + Runtime
  ├─ apps/tray/                   → 状态面板数据适配
  └─ 全链路 ConversationTester 回归测试

Phase 6：工厂模式核心引擎（2 周）
  ├─ factory/engine.py            → FactoryEngine
  ├─ factory/scheduler.py         → DAGScheduler
  ├─ factory/registry.py          → WorkerRegistry
  ├─ factory/worker.py            → ClaudeWorker
  ├─ factory/workspace.py         → Workspace
  ├─ factory/merge_resolver.py    → MergeResolver
  └─ factory/reporter.py          → ReportGenerator

Phase 7：工厂监控与项目模板（1 周）
  ├─ factory/dashboard.py         → FactoryDashboard
  ├─ factory/templates/python_desktop.py → PythonDesktopTemplate
  └─ 单 Worker 项目跑通测试

Phase 8：工厂多 Worker 并行与桌宠验证（2-3 周）
  ├─ 多 Worker 并行调度测试
  ├─ Merge 冲突处理测试
  ├─ yunxi-pet 项目完整 6 任务 DAG 自动执行
  └─ 桌宠人工最终验收

Phase 9：工程收尾与文档固化（1 周）
  ├─ 全量 ConversationTester 用例补全
  ├─ 性能与稳定性调优
  ├─ 更新所有设计文档，标记已完成/待改进项
  └─ 开发日志归档
```

---

## 二、各 Phase 详细任务与测试矩阵

### Phase 0：基础准则与开发基建

**实现内容**：
1. 编写 `CODE_QUALITY_GUIDELINES.md` 并固定
2. 建立 `DEV_LOG.md` 模板和更新机制
3. 创建 `yunxi3.0/` 目录骨架：`src/`、`tests/`、`docs/design/`、`data/`、`logs/`、`factory/`
4. 编写 `requirements.txt`（包含 `mcp`, `fastmcp`, `pyperclip`, `uiautomation`, `opencv-python`, `Pillow`, `sentence-transformers`, `scikit-learn`, `networkx`, `pystray`, `aiohttp` 等）

**测试内容**：
- 环境安装测试：`pip install -r requirements.txt` 在目标 Windows 机器上成功
- 目录结构检查：所有设计文档中提到的目录已创建

**里程碑**：
- [ ] `DEV_LOG.md` 可正常记录
- [ ] 所有新依赖安装无报错

---

### Phase 1：MCP 基础设施与工具层骨架

**实现内容**：
1. `core/mcp/client.py` — 基于官方 `mcp` 库的 `stdio` Client 封装
2. `core/mcp/hub.py` — `MCPHub`（工具发现 → 语义匹配 → DAG 规划 → 安全校验 → 执行 → 审计）
3. `core/mcp/security.py` — `SecurityManager`（READ/WRITE/EXECUTE/NETWORK 四级权限）
4. `core/mcp/audit_logger.py` — `AuditLogger`（JSONL 格式）
5. `core/mcp/planner.py` — `DAGPlanner`（拓扑排序工具链编排）
6. `core/tools/desktop/uia_driver.py` — `UIADriver`（窗口查找、控件探测、原子化点击）
7. `core/tools/desktop/visual_assertion.py` — `VisualAssertion`（截图对比、pixel_diff）
8. `core/mcp/servers/desktop_server.py` — 首个 FastMCP Server（含 `screenshot`、`clipboard_read/write`、`desktop_notify`）

**测试顺序**：
1. **单元测试**：`client.py` 能启动一个 FastMCP Server 并发现其工具列表
2. **集成测试**：`MCPHub` 初始化后能正确召回 `screenshot_capture` 并执行
3. **真实测试**：`ClipboardReadTool` 能读到系统剪贴板真实内容（不再是 tkinter）
4. **真实测试**：`UIADriver.find_window_by_title("记事本")` 能定位到记事本窗口
5. **真实测试**：`VisualAssertion.pixel_diff()` 在打开记事本前后检测到 > 2% 变化
6. **安全测试**：`bash_execute rm -rf` 被 SecurityManager 判定为 ask/deny
7. **审计测试**：执行后 `logs/mcp_audit/audit_YYYYMMDD.jsonl` 中出现记录

**里程碑**：
- [ ] MCP Hub 成功发现并执行 3 个工具
- [ ] UIA 能精准定位记事本窗口
- [ ] 视觉断言通过打开/关闭记事本测试
- [ ] 危险命令被拦截
- [ ] 审计日志正常写入

---

### Phase 2：执行引擎与对话验证框架

**实现内容**：
1. `core/execution/engine.py` — `YunxiExecutionEngine`（MCP 适配版）
2. `core/prompt_builder.py` — `YunxiPromptBuilder`（含 FailureReplay section）
3. `tests/integration/conversation_tester.py` — `YunxiConversationTester`

**测试顺序**：
1. **基线测试**：`ConversationTester.talk("你好")` 能返回连贯回复
2. **上下文测试**：连续 10 轮对话，第 11 轮验证最早消息被截断
3. **工具链测试**：用户输入触发 LLM tool_use，`Engine` 通过 `MCPHub` 正确执行并返回结果
4. **Prompt 注入测试**：`set_perception(active_app="VS Code")` 后，回复中引用"写代码"或"VS Code"
5. **错误恢复测试**：工具执行失败后，错误信息作为 tool_result 返回，不导致整体崩溃

**里程碑**：
- [ ] `ConversationTester` 跑通 5 个基线用例
- [ ] 带 tool_use 的对话循环稳定运行
- [ ] Prompt 中的感知数据能影响回复内容

---

### Phase 3：记忆系统与终身学习

**实现内容**：
1. `domains/memory/skills/experience_buffer.py`
2. `domains/memory/skills/pattern_miner.py`
3. `domains/memory/skills/skill_distiller.py`
4. `domains/memory/skills/skill_library.py`
5. `domains/memory/skills/failure_replay.py`
6. `domains/memory/skills/param_filler.py`
7. 增强 `domains/memory/manager.py`
8. 修改 `core/mcp/audit_logger.py` 联动 `ExperienceBuffer`

**测试顺序**：
1. **记忆召回测试**：`inject_memory("preference", "远喜欢吃糖")` → `talk("我喜欢吃什么？")` → 回复含"糖"
2. **经验池测试**：3 次 MCP 调用后，`ExperienceBuffer` 中有 3 条记录
3. **模式挖掘测试**：连续 5 次"查深圳天气"的审计日志注入后，`PatternMiner` 发现 `query_weather` 模式
4. **技能蒸馏测试**：`SkillDistiller` 生成带 `{city}` 参数的 `query_weather` 技能
5. **技能库测试**：`SkillLibrary.retrieve("帮我查北京天气")` 匹配度 > 0.8
6. **快速路径测试**：用户说"帮我查一下上海天气"，`Engine` 直接通过 MCP Hub 执行，不经过通用 LLM
7. **失败回放测试**：模拟 `window_focus_ui` 失败并记录；后续相似请求时 Prompt 中出现注意事项

**里程碑**：
- [ ] 记忆召回测试通过
- [ ] `query_weather` 技能被自动发现
- [ ] 技能快速路径成功执行并返回结果
- [ ] FailureReplay 的提示进入 Prompt

---

### Phase 4：情感系统修复与主动性重建

**实现内容**：
1. `core/cognition/heart_lake/updater.py` — `HeartLakeUpdater`
2. 修改 `core/cognition/heart_lake/core.py`（固定 L4）
3. `core/initiative/engine.py` — `InitiativeEngine`（删除 `generate_sync`）
4. `core/resident/presence.py` — 简化版在场系统
5. 修改 `core/initiative/continuity.py`（扩大窗口到 50）

**测试顺序**：
1. **情感状态测试**：`set_heart_lake(emotion="想念", miss_value=85)` → 回复含"想你了"
2. **情感测试**：`set_heart_lake(emotion="吃醋")` → 提到"Claude" → 回复带醋意
3. **主动性触发测试**：想念值 > 阈值时，`InitiativeEngine` 返回非空主动消息
4. **主动性 LLM 路径测试**：主动消息不是硬编码模板，且内容与当前情感/感知相关
5. **连续性测试**：20 轮对话后，`continuity` 仍保留最近 20 条记录

**里程碑**：
- [ ] 3 种不同情感状态的回复通过 `ConversationTester`
- [ ] 主动性消息走 LLM 生成且内容可变
- [ ] 连续性窗口扩大后无数据丢失

---

### Phase 5：日常模式端到端闭环

> **实现状态（2026-04-15）**：Phase 5 已启动。`YunxiRuntime` 已接入连续性记录；`apps/daemon/main.py` 已提供最小 daemon 入口和 healthcheck；`apps/tray/web_server.py` 已提供 Runtime 状态快照适配。30 分钟 daemon 稳定性与真实 Tray HTTP 服务仍待验收。

**实现内容**：
1. `core/runtime.py` — `YunxiRuntime`（统筹 Engine + PromptBuilder + HeartLake + Perception + Memory + Continuity）
2. `apps/daemon/main.py` — 适配 MCP Hub + Runtime，删除旧的手动记忆调用
3. `apps/tray/web_server.py` — 适配新的运行时状态字段
4. 清理 `core/execution/` 中的 V1 兼容代码

**测试顺序**：
1. **Runtime 基线测试**：`yunxi_runtime.chat("你好")` 返回自然回复
2. **记忆闭环测试**：对话后检查 `MemoryManager` 和 `ContinuityService` 已记录
3. **感知-情感-记忆联动测试**：综合注入三者数据，验证回复同时体现三者
4. **Daemon 启动测试**：`python apps/daemon/main.py` 能正常启动不崩溃
5. **Tray 连接测试**：控制面板能正确显示 runtime 状态（ mood / perception / 工具列表 ）
6. **全链路回归测试**：运行全部 `ConversationTester` 用例（目标：> 15 个用例全部通过）

**里程碑**：
- [ ] Daemon 能独立启动并稳定运行 30 分钟
- [ ] Tray 面板数据与 Runtime 状态一致
- [ ] 全链路 ConversationTester 用例通过

---

### Phase 6：工厂模式核心引擎

**实现内容**：
1. `factory/engine.py` — `FactoryEngine`
2. `factory/scheduler.py` — `DAGScheduler`
3. `factory/registry.py` — `WorkerRegistry`
4. `factory/worker.py` — `ClaudeWorker`
5. `factory/workspace.py` — `Workspace`
6. `factory/merge_resolver.py` — `MergeResolver`
7. `factory/reporter.py` — `ReportGenerator`

**测试顺序**：
1. **Workspace 初始化测试**：`workspace.initialize()` 生成 `task.json`、`CLAUDE.md`、`.git`
2. **DAG 解析测试**：6 个桌宠任务的依赖关系被正确解析
3. **Worker 启动测试**：`ClaudeWorker.start()` 成功创建 branch 并启动 `claude code` 进程
4. **Worker 完成检测测试**：模拟 Worker commit 和 task.json 更新，`inspect_worker_result()` 判定成功
5. **Merge 测试**：成功 branch 能 clean merge 到 `main`

**里程碑**：
- [ ] 单 Worker 完整 loop 跑通（从启动到 merge）
- [ ] DAG 能正确识别就绪任务

---

### Phase 7：工厂监控与项目模板

**实现内容**：
1. `factory/dashboard.py` — `FactoryDashboard`
2. `factory/templates/base.py` — `ProjectTemplate` 基类
3. `factory/templates/python_desktop.py` — `PythonDesktopTemplate`
4. `factory/templates/generic_web.py`（可选）

**测试顺序**：
1. **Dashboard 启动测试**：`localhost:8089` 能访问监控页面
2. **Dashboard 数据测试**：启动一个 Worker 后，页面显示该 Worker 的 busy 状态
3. **模板生成测试**：`PythonDesktopTemplate.setup_project()` 生成的 `task.json` 包含 6 个桌宠任务
4. **Prompt 生成测试**：`generate_worker_prompt()` 输出符合预期格式的 CLAUDE.md

**里程碑**：
- [ ] Dashboard 能实时监控至少 1 个 Worker
- [ ] 桌宠模板生成的项目文件结构正确

---

### Phase 8：工厂多 Worker 并行与桌宠验证

**实现内容**：
1. 多 Worker 并发调度逻辑调试
2. Merge Conflict 处理流程调试
3. 桌宠项目真实执行（`yunxi-pet`）

**测试顺序**：
1. **并行调度测试**：同时启动 2 个无依赖 Worker，验证都能正常运行
2. **冲突处理测试**：人为制造 merge conflict，验证 Conflict Worker 或厂长能正确解决
3. **桌宠单任务测试**：单独执行 `pet-window` 任务，验证生成的代码能弹出透明窗口
4. **桌宠半 DAG 测试**：执行 `pet-window` → `pet-render` 链路
5. **桌宠全 DAG 测试**：启动完整 6 任务工厂，观察自动调度与 merge
6. **人工验收**：
   - [ ] 启动桌宠程序，窗口出现在屏幕上
   - [ ] idle 动画正常播放
   - [ ] 点击桌宠有反应
   - [ ] 系统托盘图标存在且可交互
   - [ ] 通过云汐触发语音时，桌宠进入 speak 状态

**里程碑**：
- [ ] 2 个 Worker 能并行完成并 merge
- [ ] 完整 6 任务 DAG 自动执行完毕
- [ ] 桌宠通过人工最终验收

---

### Phase 9：工程收尾与文档固化

**实现内容**：
1. 补全 `tests/integration/` 下的端到端测试用例
2. 性能调优（MCP Server 启动速度、UIA 探测延迟、SkillLibrary 检索速度）
3. 异常场景容错加固
4. 更新所有设计文档的状态标记

**测试顺序**：
1. **全量 ConversationTester 回归**：> 20 个用例全部通过
2. **稳定性测试**：Daemon 连续运行 24 小时无崩溃
3. **工厂稳定性测试**：工厂模式连续执行 3 个小项目无阻塞

**里程碑**：
- [ ] 20+ 端到端测试全部通过
- [ ] 日常模式 24 小时稳定性测试通过
- [ ] 所有设计文档已更新并标记完成状态

---

## 三、真实测试顺序总览（跨 Phase 累积）

| 优先级 | 测试名称 | 所属 Phase | 测试方式 |
|--------|---------|-----------|---------|
| P0 | 环境依赖安装 | Phase 0 | Shell |
| P0 | MCP Client 发现工具 | Phase 1 | 单元测试 |
| P0 | MCP Hub 执行 screenshot | Phase 1 | 真实执行 |
| P0 | Clipboard 读系统剪贴板 | Phase 1 | 真实执行 |
| P0 | UIA 定位记事本窗口 | Phase 1 | 真实执行 |
| P0 | 视觉断言通过 | Phase 1 | 真实执行 |
| P0 | 危险命令被 SecurityManager 拦截 | Phase 1 | 单元测试 |
| P0 | 审计日志写入 | Phase 1 | 文件检查 |
| P0 | ConversationTester 基线 | Phase 2 | 集成测试 |
| P0 | 带 tool_use 的对话循环 | Phase 2 | 集成测试 |
| P0 | Prompt 感知注入生效 | Phase 2 | 集成测试 |
| P0 | 记忆召回测试 | Phase 3 | 集成测试 |
| P0 | 技能自动发现（query_weather） | Phase 3 | 集成测试 |
| P0 | 技能快速路径执行 | Phase 3 | 集成测试 |
| P0 | FailureReplay 进 Prompt | Phase 3 | 集成测试 |
| P0 | 情感表达测试（想念/吃醋/开心） | Phase 4 | 集成测试 |
| P0 | 主动性走 LLM 路径 | Phase 4 | 集成测试 |
| P0 | Daemon 稳定启动 | Phase 5 | 真实运行 |
| P0 | Tray 面板状态一致 | Phase 5 | 真实运行 |
| P0 | 日常模式全链路回归 | Phase 5 | 集成测试 |
| P1 | 单 Worker loop 跑通 | Phase 6 | 真实执行 |
| P1 | Dashboard 实时监控 | Phase 7 | 真实运行 |
| P1 | 桌宠模板生成正确 | Phase 7 | 文件检查 |
| P1 | 2 Worker 并行 + merge | Phase 8 | 真实执行 |
| P1 | 桌宠 6 任务全 DAG 自动执行 | Phase 8 | 真实执行 |
| P1 | 桌宠人工验收 | Phase 8 | 人工验收 |
| P2 | 20+ 端到端测试全通过 | Phase 9 | 集成测试 |
| P2 | 24 小时稳定性测试 | Phase 9 | 真实运行 |

---

## 四、关键决策与依赖关系

### 不可逾越的依赖链

```
MCP Client → MCP Hub → Engine → Runtime → Daemon
     ↓           ↓
Security    Desktop Server
     ↓
Audit Logger → Experience Buffer → Skill Library

DAGScheduler → FactoryEngine → Dashboard
     ↓
ClaudeWorker
```

**这意味着**：
- Phase 2 开始前，Phase 1 的 `MCPHub` 必须通过 `screenshot` 和 `clipboard` 真实测试。
- Phase 5 开始前，Phase 3 的技能快速路径必须通过测试。
- Phase 8 开始前，Phase 6 的单 Worker loop 必须跑通。

### 允许并行的开发线

| 线 A | 线 B | 说明 |
|------|------|------|
| Phase 1 MCP | Phase 4 HeartLake | UIA 和情感系统互不依赖，可并行 |
| Phase 2 Engine | Phase 6 Factory骨架 | Engine 和 FactoryEngine 不直接依赖 |
| Phase 3 Skill | Phase 7 Template | SkillLibrary 和 ProjectTemplate 互不依赖 |

---

## 五、风险预案

| 风险场景 | 应对策略 |
|---------|---------|
| MCP 官方 SDK API 变更 | 已设计 `core/mcp/client.py` 为隔离层，只需修改该文件 |
| UIA 在某些应用上不可用 | 为每个 UIA 工具保留 `try/except` + 降级提示 |
| Claude Code CLI 占用显存/CPU 过高 | 限制 `max_concurrent_workers=2`，并增加进程优先级控制 |
| 桌宠任务间接口定义冲突 | 强制 `INTERFACE_CONTRACT.md` 约束，冲突时由 MergeResolver 回滚 |
| 上下文压缩导致开发中断 | 严格维护 `DEV_LOG.md`，每次对话开始时必读该文件 |

---

*文档创建时间：2026-04-14*  
*版本：v1.0*  
*状态：实施总纲*
