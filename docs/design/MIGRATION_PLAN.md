# 云汐 3.0 迁移与实施总计划（集成研究成果版）

> **范围**：本计划涵盖日常模式、情感系统、记忆系统、主动性系统、执行层、Prompt 构建器、工具层、对话验证框架、工厂模式。  
> **核心原则**：修复接线，严格工程化，行为验证，深度融合已有研究成果但全部在 yunxi3.0 内重写实现。  
> **关键约束**：不允许跨目录依赖 `D:\ResearchProjects`，所有研究成果的核心理念在 yunxi3.0 内重新实现。

---

## 一、总体目标

云汐 2.0 的核心问题不是子系统设计不足，而是**子系统与主链路（LLM Prompt）之间的接线断裂**。3.0 的策略是：

1. **保留并继承** 2.0 中设计正确、逻辑完备的子系统核心（HeartLake 动力学、感知数据采集、记忆存储结构、LLM 路由）。
2. **彻底重构** 这些子系统的"接入层"，确保它们的数据能稳定、直接、无损耗地进入 LLM Prompt。
3. **深度融合研究成果**：将 `03_MACP`、`13_ComputerUseAgent`、`14_MCP_Tool_Hub`、`15_LifelongLearning` 的核心思想融入 3.0 架构，但全部在 yunxi3.0 代码库内重新实现。
4. **简化执行层**，删除 V1/V2 双轨、过度抽象的 State Machine、未实际触发的复杂异常恢复分支。
5. **改革测试方式**，建立"对话验证框架"，以真实回复质量为唯一验收标准。

---

## 二、研究成果与 yunxi3.0 的整合策略

### 2.1 `03_multi_agent_collaboration_protocol_v2` → 工厂模式底层引擎

**借鉴内容**：
- DAG 调度引擎（依赖解析、就绪任务发现、状态机管理）
- AgentRegistry（Agent 生命周期注册与状态跟踪）
- WebDashboard（2 秒轮询的监控面板）
- 领域模板系统（DomainTemplate 分离业务逻辑与调度引擎）

**3.0 实现方式**：
- 在 `yunxi3.0/factory/` 内重写 `DAGScheduler`、`WorkerRegistry`、`FactoryDashboard`。
- 不直接 import `ResearchProjects/03_macp/`，而是**参考其接口设计和状态机逻辑**，用更符合工厂模式的命名和流程重写。
- Claude Code CLI 被包装为一种特殊的 "ExternalWorker"，纳入 WorkerRegistry 统一管理。

### 2.2 `13_computer_use_agent` → 桌面工具层与视觉验证

**借鉴内容**：
- UIA（Windows UI Automation）控件树探测，替代硬编码 `ctypes`
- 视觉断言（操作前后截图对比，pixel_diff + 自适应阈值）
- 原子化执行（`hover → pause → click → pause`）
- GUI Macro（成功操作序列的参数化复用）
- 任务评估器（用 UIA 独立读取控件内容验证结果）

**3.0 实现方式**：
- 在 `yunxi3.0/core/tools/desktop/` 内重写 UIA 感知模块、视觉断言模块、GUI Macro 执行器。
- `window_control`、`app_launch`、`media_control` 等工具全部基于 UIA 重新实现。
- 桌宠工厂项目的 E2E 验证采用"UIA 控件探测 + 截图断言"双轨验证，替代单纯的人工截图验收。
- 日常模式中，高风险桌面操作（如点击、窗口切换）默认启用视觉断言，失败时自动重试或降级。

### 2.3 `14_mcp_tool_hub` → 日常模式工具全面 MCP 化

**借鉴内容**：
- MCP（Model Context Protocol）标准工具发现与调用
- DAGPlanner（工具链自动编排，识别输入输出依赖）
- SemanticMatcher（BGE Embedding + Keyword Gate 精准召回）
- SecurityManager（safe/caution/dangerous 三级风险 + 审计日志）
- AuditLogger（JSONL 持久化）

**3.0 实现方式**：
- 在 `yunxi3.0/core/mcp/` 目录下重写 MCP Client、Hub、SecurityManager、AuditLogger、Planner。
- 所有日常工具（bash、file、clipboard、screenshot、desktop_notify 等）全部包装为 **FastMCP Server**。
- `YunxiExecutionEngine` 不再直接调用 `tool.execute()`，而是通过 MCP Hub 的 `DAGPlanner` 规划工具链，再经 `SecurityManager` 校验后执行。
- 工具调用结果写入统一格式的 `audit.jsonl`，作为 15 号项目终身学习的数据源。

### 2.4 `15_agent_lifelong_learning` → 记忆系统升级为技能自动发现

**借鉴内容**：
- ExperienceBuffer + PatternMiner（Sentence-BERT + K-Means 发现重复模式）
- SkillDistiller（将具体案例抽象为参数化技能模板）
- SkillLibrary（Embedding 索引 + 语义检索 + 冲突消解 + 成功率追踪）
- FailureReplay（注入历史注意事项，避免重复犯错）

**3.0 实现方式**：
- 在 `yunxi3.0/domains/memory/skills/` 目录下重写 `ExperienceBuffer`、`PatternMiner`、`SkillDistiller`、`SkillLibrary`、`FailureReplay`。
- `MemoryManager` 新增 `SkillLibrary` 子模块。
- 每日后台任务扫描 MCP 审计日志，用 `PatternMiner` 聚类意图-动作模式，`SkillDistiller` 生成技能模板。
- 当用户请求与某技能高度匹配时，`YunxiExecutionEngine` 可直接调用技能对应的工具链 Macro，绕过通用 LLM 推理，提升响应速度和稳定性。
- `YunxiPromptBuilder` 的 `_build_memory_section()` 除了注入偏好/情景，还会注入 `FailureReplay` 中的相关注意事项。

### 2.5 `02_llm_agent_security_sandbox` → 统一安全治理框架

**借鉴内容**：
- 四级权限模型（READ / WRITE / EXECUTE / NETWORK）
- 操作审计图谱与风险事件告警

**3.0 实现方式**：
- 在 `yunxi3.0/core/security/` 目录下重写统一的安全治理框架。
- 所有 MCP Server 注册时必须声明权限级别（`read`/`write`/`execute`/`network`）。
- `SecurityManager` 根据用户上下文（如当前是日常模式还是工厂模式）动态调整权限边界。
- 高风险操作（`write` + `execute` 组合）触发显式确认或降级到沙箱目录执行。

---

## 三、从 yunxi2.0 的继承清单

### 3.1 直接继承（代码几乎不变）

| 模块 | 2.0 位置 | 继承理由 |
|------|---------|---------|
| **多 LLM Provider 适配层** | `adapters/` + `core/services/llm/` | 路由设计成熟，支持 MiniMax / Moonshot / Ollama 热切换。 |
| **感知数据采集** | `domains/perception/coordinator.py` 及其子模块 | 已经能稳定获取 CPU/窗口/天气/RSS/剪贴板/时间节律。 |
| **HeartLake 情感动力学核心** | `core/cognition/heart_lake/core.py` + `appraisers.py` + `dynamics.py` | OCC 评估、二级情绪混合、PAD 空间更新逻辑是正确的。 |
| **记忆存储底层** | `domains/memory/` 下的各 Store（`semantic/store.py`, `episodic/store.py`, `autobiographical/store.py`, `perceptual/store.py`） | 存储结构和领域模型（`MemoryEntry`, `UserProfile`, `Episode` 等）无需推翻重建。 |
| **Tray / WebUI 基础** | `apps/tray/` | 托盘常驻和控制面板已跑通，只需调整展示的数据字段。 |
| **连续性持久化结构** | `core/initiative/continuity.py` | 状态文件结构（`exchanges`, `unanswered_proactive_count`, `open_threads`）可用。 |

### 3.2 需要重构（保留核心设计，重写接入层）

| 模块 | 2.0 位置 | 重构重点 |
|------|---------|---------|
| **执行引擎** | `core/execution/query_loop.py` + `query_loop_executor.py` + `query_engine.py` | 删除 V1 兼容、State Machine、过度分支，简化为单一循环；适配 MCP 工具调用协议。 |
| **Prompt 构建** | `core/execution/companion_runtime_support.py`（被滥用为 Prompt 工厂） | 拆出独立的 `YunxiPromptBuilder`，统一拼装所有子系统数据。 |
| **消息生成器** | `core/initiative/generator.py` | 删除 `generate_sync()` 死代码，所有生成（被动+主动）统一走 LLM。 |
| **在场系统** | `core/resident/presence.py` | 修复 sync/async 混用，删除私有字段篡改，统一上下文记录。 |
| **记忆管理器接口** | `domains/memory/manager.py` | 统一对外接口，新增 SkillLibrary 子模块，确保执行层能直接调用并注入 Prompt。 |
| **工具层** | `core/tools/` | **全面 MCP 化**：所有工具包装为 FastMCP Server；桌面工具基于 UIA 重写；引入 DAGPlanner 和安全治理框架。 |
| **测试体系** | `tests/` | 新增 `tests/integration/conversation_tester.py`，端到端行为验证为主。 |

### 3.3 彻底删除

| 模块 | 删除理由 |
|------|---------|
| `core/execution/query_engine.py` (V1) | 双轨制是债务根源。 |
| `core/execution/context_manager.py` (V1) | 已被 V2 替代，且无维护价值。 |
| `core/execution/state_machine.py` 中的过度抽象 | 函数式不可变 `QueryState` 在 Python 中无实际收益，徒增复杂度。 |
| `core/initiative/generator.py` 中的 `generate_sync()` | 运行时 100% 走此死代码，导致情感/感知/记忆完全不影响生成结果。 |
| 亲密度成长算法与升级仪式感 | 策略简化为固定 L4，删除成长/衰减/升级触发逻辑。 |
| `core/execution/companion_runtime_support.py` 的上帝类结构 | 拆散为独立模块。 |
| `core/tools/` 中的硬编码 ctypes 实现 | 由 UIA 和 MCP Server 替代。 |

---

## 四、模块依赖与实施顺序（修正版）

```
Phase 1：基础设施
  ├─ core/mcp/                    → MCP Client / Hub / Security / Audit（参考 14 重写）
  ├─ core/security/               → 四级权限模型（参考 02 重写）
  └─ core/tools/desktop/          → UIA 基础模块（参考 13 重写）

Phase 2：日常模式骨架
  ├─ PROMPT_BUILDER_DESIGN.md     → 统一 Prompt 构建器
  ├─ EXECUTION_ENGINE_DESIGN.md   → 简化执行层，适配 MCP Hub
  └─ CONVERSATION_TESTER_DESIGN.md → 对话验证框架

Phase 3：日常模式血肉
  ├─ MEMORY_INTEGRATION_DESIGN.md → 记忆 + SkillLibrary（参考 15 重写）
  ├─ INITIATIVE_REPAIR_DESIGN.md  → 主动性修复
  └─ HEART_LAKE_L4_DESIGN.md      → 情感特化（固定 L4）

Phase 4：工具层确认闭环
  ├─ TOOLS_REFACTOR_DESIGN.md     → MCP Server 实现、DAGPlanner、视觉断言、GUI Macro
  └─ Desktop MCP 基础工具、pending confirmation 和错误人格化验收

Phase 5：日常入口与状态控制
  ├─ 飞书作为唯一日常对话入口
  ├─ WebUI/Tray 改为状态、日志、healthcheck 和工厂入口
  └─ 分层感知与 deep healthcheck

Phase 6：电脑能力工具生态扩展
  ├─ Browser MCP             → 浏览器打开、搜索、网页读取、链接提取、基础网页操作
  ├─ Filesystem/Document MCP → 文件读写、目录整理、grep/glob、docx/xlsx/pdf 降级读取
  ├─ GUI Agent MCP           → UIA 观察、点击、输入、热键、GUI Macro
  └─ 跳过飞书的直接工具矩阵验收

Phase 7：飞书日常模式浸泡测试
  ├─ 飞书聊天 + 主动消息 + 工具确认
  ├─ 浏览器 / 文档 / GUI fallback 抽样真实触发
  └─ 重启后记忆连续性检查

Phase 8：工厂模式
  ├─ FACTORY_MODE_DESIGN.md       → 基于 MACP 核心逻辑重写（参考 03 重写）
  └─ 以桌宠项目为验证任务

Phase 9：终身学习闭环
  └─ domains/memory/skills/       → PatternMiner + SkillDistiller + FailureReplay（参考 15 重写）
```

---

## 五、关键设计决策记录（新增/修正）

| 决策 | 选择 | 理由 |
|------|------|------|
| 工厂底层引擎 | 重写 MACP 核心逻辑 | 借鉴 03 的 DAG 调度与监控设计，但适配 Claude Code CLI 子进程模型。 |
| 工具调用协议 | **全面 MCP 化** | 借鉴 14 的动态发现、DAG 编排、安全策略，实现可扩展、可审计的工具层。 |
| 桌面操作后端 | **UIA 替代 ctypes** | 借鉴 13 的精确控件探测和视觉断言，解决 2.0 窗口工具脆弱问题。 |
| 记忆增强 | **SkillLibrary** | 借鉴 15 的终身学习框架，让云汐从经验中生成可执行技能。 |
| 安全框架 | 四级权限 + 审计日志 | 借鉴 02 和 14，统一所有工具的风险评估。 |
| 执行后端 | 单一 `YunxiExecutionEngine` | 删除双轨，通过 MCP Hub 调用工具。 |
| 上下文压缩 | `recent_messages(limit=20)` | 个人使用场景下，20 轮通常不会超 token；超长记忆由 Memory/Skill 补充。 |
| 情感状态 | 固定 L4 伴侣 | 删除抽象的亲密度成长，专注情绪波动。 |
| 主动性生成 | 统一走 LLM | 删除模板 fallback，让主动消息能真正结合情境。 |
| 测试方式 | 对话验证框架 + 端到端测试 | 以真实回复质量为验收标准。 |

---

## 六、风险与规避（新增）

| 风险 | 规避措施 |
|------|---------|
| MCP 生态快速迭代导致 API 不稳定 | 封装一层 `yunxi3.0/core/mcp/client.py` 适配器，隔离官方 SDK 变更。 |
| UIA 在部分 Windows 应用上不可用 | 保留 `BasicFallbackProvider` 作为降级，但明确标注精度下降。 |
| SkillLibrary 聚类结果不稳定 | 设置人工审核阈值：只有置信度 > 0.8 的模式才会自动转为技能。 |
| 工厂 Worker 并发导致 merge conflict | 设计明确的接口契约文件（`INTERFACE_CONTRACT.md`），冲突时优先启动 Conflict Worker。 |
| 研究成果代码与 yunxi3.0 风格不一致 | 严格约束：所有代码必须在 yunxi3.0 目录内重写，不允许直接 import ResearchProjects。 |

---

## 七、文件清单

本计划关联以下设计文档：

1. `PROMPT_BUILDER_DESIGN.md` — Prompt 构建器设计
2. `EXECUTION_ENGINE_DESIGN.md` — 执行层简化设计（适配 MCP）
3. `CONVERSATION_TESTER_DESIGN.md` — 对话验证框架设计
4. `MEMORY_INTEGRATION_DESIGN.md` — 记忆系统接入 + SkillLibrary 设计
5. `INITIATIVE_REPAIR_DESIGN.md` — 主动性系统修复
6. `HEART_LAKE_L4_DESIGN.md` — 情感特化（L4 固定）
7. `TOOLS_REFACTOR_DESIGN.md` — 工具层 MCP 化 + UIA + 视觉断言
8. `FACTORY_MODE_DESIGN.md` — 工厂模式（基于 MACP 重写）
9. `SECURITY_FRAMEWORK_DESIGN.md` — 统一安全治理框架（新增，待补充）

---

*文档创建时间：2026-04-14*  
*最后更新时间：2026-04-16*
*版本：v2.1*
