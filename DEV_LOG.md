# 云汐 3.0 开发日志

> **用途**：记录当前开发状态、阻塞问题、下一步计划。  
> **读取时机**：每次新对话开始时，必须首先阅读本文件最新内容。  
> **更新时机**：每完成一个显著里程碑、遇到阻塞、或转换 Phase 时，必须更新本文件。  
> **更新方式**：使用工具直接修改本文件，在顶部追加新的日志条目。

---

### [2026-04-15] 重要待实现：yunxi2.0 人格与主动性资产迁移清单已建立

Anchor: YUNXI2_PERSONA_INITIATIVE_MIGRATION

**状态**：重要 / 待实现 / P0 阻塞项。当前只完成设计同步，尚未开始代码迁移。

**背景结论**：
- yunxi3.0 当前已经打通 Runtime、LLM、MCP、Memory、HeartLake、主动 tick 和 daemon 的最小闭环，但人格与主动性仍是偏工程化骨架。
- yunxi2.0 中已经存在更完整的云汐人格资产、用户关系档案、生活事件库、三层主动事件系统、表达姿态和伴侣连续性设计。
- 如果不先迁移这些资产，继续推进 Phase 5/6 会让云汐偏向“高级脚本执行程序”，不符合“住在电脑里的女友”的设计初衷。

**已完成文档同步**：
- 新增 `docs/design/PERSONA_INITIATIVE_MIGRATION_PLAN.md`，列出 2.0 资产来源、3.0 目标模块、优先级、验收标准和实现顺序。
- 更新 `docs/design/MASTER_EXECUTION_PLAN.md`，将该迁移标记为 Phase 4.5 / Phase 5 的 P0 阻塞项。
- 更新 `docs/design/INITIATIVE_REPAIR_DESIGN.md`，明确当前主动链路只是“真实 LLM 底线完成”，还缺 2.0 的事件系统、decider、generator、expression context、continuity。
- 更新 `docs/design/PROMPT_BUILDER_DESIGN.md`，要求 PromptBuilder 接入结构化 persona profile、relationship profile、initiative event 和 expression context。

**迁移范围**：
1. `data/persona/*`：迁移云汐人格核心，但高亲密/成人表达内容必须先做边界审查，禁止原样注入主 prompt。
2. `data/relationship/USER.md`：迁移远的称呼、学校、专业、家乡、兴趣、讨厌的表达方式和长期偏好。
3. `data/life_events/life_events.json`：迁移并清洗 100+ 生活事件，作为 LLM 主动生成素材。
4. `core/initiative/event_system.py`：重建三层事件系统：内在生活、共同兴趣、混合事件。
5. `core/initiative/decider.py`：迁移多维主动决策：时间、情绪、presence、资源、预算、open_threads、未回复主动次数。
6. `core/initiative/generator.py`：迁移主动生成上下文组织能力，但禁止恢复固定 fallback 文案。
7. `core/initiative/expression_context.py`：迁移关系感表达姿态。
8. `core/initiative/continuity.py`：补齐持久化、relationship summary、emotional summary、open_threads、recent topics。

**下一步实现顺序**：
1. P0-A：迁入 persona / relationship profile，并接入 PromptBuilder。
2. P0-B：补齐 Continuity 持久化与 open_threads。
3. P0-C：迁入生活事件库并实现三层事件系统。
4. P0-D：重建主动 decider / generator / expression context。
5. P0-E：使用本地 Ollama 和至少一种云端模型做真实 LLM 验收。

**验收要求**：
- 不能只做函数运行测试，必须做真实 LLM 对话和主动消息测试。
- 至少覆盖本地 Ollama 路径和一个云端模型路径。
- 测试必须判断人格、关系记忆、主动话题、克制 follow-up 和反工具化是否真的符合设计。

---

## 当前快照（务必保持最新）

| 字段 | 当前值 |
|------|--------|
| **当前 Phase** | Phase 4.5 / Phase 5 Hardening |
| **当前聚焦模块** | 全阶段设计一致性修复：真实感知、MCP 完整性、记忆学习、情感主动性、日常闭环 |
| **最近一次更新** | 2026-04-15 |
| **当前状态** | Hardening 已开始：真实感知、MCP 工具列表封装、daemon Desktop MCP 初始化、记忆离线降级、Ollama LLM provider 已落地；Phase 5 仍不能视为完成 |
| **当前阻塞** | P0：情感/主动性规则化、MCP 工具层未全面化、Continuity 未持久化、Tray/WebUI 未真实接入、Ollama embedding 语义向量未接入 |
| **下一步计划** | 1. 重构情感事件评估 2. Continuity 持久化与 open threads 3. Ollama embedding 语义向量 provider 4. 补 MCP 工具层缺口 5. 接入真实 Tray/WebUI |
| **最近通过测试** | 本地回归 63 passed；Ollama daemon healthcheck 通过且不再触发 HuggingFace 请求 |
| **风险标记** | 之前“正式进入 Phase 5”的判断过早；当前必须先做 Phase 0-5 设计一致性修复 |

---

## 日志条目（按时间倒序，新的写在最上面）

### [2026-04-15] Hardening 第一批修复：真实感知、Ollama、本地降级

**完成内容**：
- `PerceptionCoordinator` 支持真实感知 provider，默认读取 Windows 前台窗口、用户 idle 时长、CPU 占用和当前时间；测试仍可注入固定快照。
- `MCPClient` / `MCPHub` 增加公开工具名列表接口，`YunxiRuntime` 不再读取 `client._connections` 私有字段，也不再静默 `pass`。
- `apps/daemon/main.py` 在启用工具时会初始化 Desktop MCP Server，并在 healthcheck/退出时释放 MCP 与 LLM 资源。
- `PatternMiner` / `SkillLibrary` 增加模型不可用时的离线降级，不再因为 HuggingFace 网络受限导致 daemon 启动失败。
- `LLMAdapter.from_env("ollama")` 支持本地 Ollama，不要求 API Key。
- Ollama Provider 改为原生 `/api/chat` 路径，并兼容 `OLLAMA_BASE_URL` 误设为 `/v1` 的情况。
- 新增真实 Ollama 集成测试，会从本机 `/api/tags` 中选择实际存在的模型执行一次真实本地 LLM 对话。
- Daemon 使用 `--provider ollama` 时默认采用 `lexical` embedding provider，避免日常启动依赖 HuggingFace 网络；后续再接 Ollama embedding 语义向量。

**本机 Ollama 探测结果**：
- `gpt-oss:20b`
- `qwen3:4b`
- `qwen3-vl:8b`

**已通过测试**：
- `python -m pytest -q tests\unit\test_perception_coordinator.py tests\integration\test_phase4_runtime.py` → 5 passed
- `python -m pytest -q tests\unit tests\integration\test_phase5_daily_mode.py` → 31 passed
- `python -m pytest -q tests\domains\memory` → 23 passed
- `python -m pytest -q tests\unit\test_execution_engine.py tests\integration\test_ollama_llm.py` → 6 passed
- `python -m pytest -q tests\unit tests\domains\memory tests\integration\test_conversation_tester_baseline.py tests\integration\test_phase4_runtime.py tests\integration\test_phase5_daily_mode.py tests\integration\test_ollama_llm.py` → 63 passed
- `$env:PYTHONPATH='D:\yunxi3.0\src'; python -m apps.daemon.main --healthcheck --disable-tool-use --skip-desktop-mcp` → 非沙箱真实运行通过
- `$env:PYTHONPATH='D:\yunxi3.0\src'; python -m apps.daemon.main --healthcheck --provider ollama --disable-tool-use --skip-desktop-mcp` → 本地 Ollama 运行通过，且不触发 HuggingFace 请求

**仍需继续修复**：
1. HeartLake / HeartLakeUpdater 仍是规则化情感系统，下一步要改为事件评估结构。
2. Continuity 仍未持久化，没有 open threads。
3. Ollama 目前只接入 LLM；embedding 已有本地词面降级，但还未接入 Ollama 语义向量。
4. Tray/WebUI 仍只是状态适配，不是真实服务。

---

### [2026-04-15] 模型策略修正：本地 Ollama 作为一等后端

**用户补充约束**：
本机已经通过 Ollama 部署了本地模型，项目设计不能只围绕云端 LLM 或 HuggingFace 在线模型。云汐作为常驻本地电脑里的女友，应该优先考虑本地可用模型能力，并在需要时再切换云端模型。

**设计修正**：
- LLM 后端必须支持：`ollama`、`moonshot`、`minimax`、`openai`。
- `ollama` 不要求 API Key，默认 base url 为 `http://localhost:11434`，优先走原生 `/api/chat`，不能假设本机 Ollama 一定启用了 OpenAI-compatible `/v1/chat/completions`。
- 日常模式应允许 `--provider ollama`，并通过 `OLLAMA_MODEL` / `OLLAMA_BASE_URL` 选择本地模型。
- 后续 embedding/记忆检索也要考虑 Ollama 本地 embedding 模型，例如 `nomic-embed-text`，不能只依赖 SentenceTransformer 在线下载。
- 真实 LLM 验收后续应分两组：云端 Kimi/MiniMax 验收、本地 Ollama 验收。只有两者之一可用时，系统也必须能启动。

**已完成代码修正**：
- `OpenAICompatibleProvider` 现在仅在存在 API Key 时发送 Authorization header，避免 Ollama 收到空 Bearer。
- `LLMAdapter.from_env("ollama")` 已支持本地模型，不再强制要求 API Key，并走 Ollama 原生 `/api/chat`。
- 新增单元测试覆盖 Ollama 配置读取。

**后续仍需补齐**：
1. 给真实 LLM 测试增加 Ollama 运行路径。
2. 给 Memory/SkillLibrary 增加 Ollama embedding provider，而不仅是 SentenceTransformer + 词面 fallback。
3. Daemon healthcheck 增加 `--provider ollama` 的本地运行验收。

---

### [2026-04-15] 全阶段设计一致性复审：暂停扩展 Phase 5，进入 Hardening

**复审结论**：
用户指出“不要把云汐做成高级脚本执行程序，而要符合住在电脑里的女友”是正确的。当前代码已经打通真实 LLM、MCP、Prompt、Runtime 的最小链路，但多个子系统仍是“能跑通的骨架”，不能按设计验收为完整实现。之前将状态表述为“Phase 5 已正式启动”可以保留为启动事实，但不能理解为 Phase 5 已完成或可继续进入后续 Phase。

**Phase 0 / 代码守则问题**：
- `src/core/execution/engine.py`、`src/core/mcp/hub.py`、`src/domains/memory/*`、`src/core/llm/*` 等核心接口仍大量使用 `Any`、裸 `Dict[str, Any]` 和 duck typing，违反“主要接口必须明确类型”的守则。
- `src/core/runtime.py` 直接读取 `mcp_hub.client._connections` 私有字段，并在异常时 `pass`，违反封装边界和错误记录要求。
- `src/core/execution/engine.py` 捕获 `Exception` 后直接返回用户可见文本，缺少结构化日志和分层错误上下文。
- 多处 IO/外部操作缺少显式 timeout 或资源清理策略，尤其是 MCP stdio、桌面工具、SQLite、LLM 调用后的上层资源生命周期。

**Phase 1 / MCP 工具层问题**：
- 设计要求“所有日常工具全面 MCP 化”，但当前只实现 `desktop_server.py`，覆盖 screenshot、clipboard、notify、app/window；缺少 file、bash、browser、web page read、media 等 MCP Server。
- `MCPHub` 的 DAGPlanner 当前只对已有 tool_call 做显式 depends_on 拓扑排序，没有实现“用户模糊意图 → 工具链规划”的能力。
- SecurityManager 只有静态 read/write/execute/network 权限，没有结合具体参数做危险操作识别，也没有真正的用户确认通道；`ask` 现在只是作为错误返回给 LLM。
- Desktop Server 中 `clipboard_*`、`desktop_notify` 捕获宽泛异常后返回字符串，缺少审计级错误结构；`app_launch_ui` 使用 `time.sleep` 和单次视觉差异判断，缺少重试/降级策略。
- `UIADriver.launch_application()` 在找不到 PATH 时使用 `shell=True`，与安全模型不一致，应改为受控 allowlist 或显式确认。

**Phase 2 / 执行引擎与对话验证问题**：
- `YunxiExecutionEngine` 的工具循环能跑通，但错误恢复偏模板化，不会基于失败类型选择重试、换工具、询问用户或解释限制。
- ConversationTester 仍以 MockLLM 为主，真实 LLM 测试存在但覆盖面不足；不能证明“真实回复质量”已满足设计。
- PromptBuilder 注入了人格、情绪、记忆、感知、工具，但更像静态拼接器，没有对上下文冲突、过长记忆、工具能力边界做结构化压缩和优先级控制。

**Phase 3 / 记忆系统与终身学习问题**：
- `MemoryManager` 的偏好、经历、承诺仅保存在内存列表，未持久化；跨会话后“女友记忆”会丢失。
- `PatternMiner` 依赖在线/本地 SentenceTransformer 初始化，缺少离线模型策略、初始化失败降级和后台学习调度。
- `SkillDistiller` / `ParamFiller` 主要靠正则和硬编码规则，技能泛化能力有限；`ParamFiller` 还存在 `Dict[str, any]` 的错误类型。
- `run_skill_learning_cycle()` 没有被 daemon/presence 调度；终身学习不是持续运行闭环。
- 技能快速路径绕过 LLM 后返回固定口吻，容易把云汐退化为“执行脚本后说一句模板话”，需要让 LLM 参与最终表达或至少注入情感上下文。

**Phase 4 / 情感与主动性问题**：
- `HeartLake` 当前是少数字段 + if/elif 阈值，不是完整情感动态模型；缺少事件评估、情绪惯性、关系语境、冲突情绪和恢复曲线。
- `HeartLakeUpdater.on_user_input()` 通过 `claude/其他ai/别的ai` 关键词触发吃醋，属于硬编码人格反应。
- `InitiativeEngine` 只是 cooldown + 事件阈值，不会结合未完成话题、用户当前工作负载、打扰成本、关系连续性做策略选择。
- 主动消息内容走真实 LLM 是正确方向，但主动“判断”层仍偏脚本化。

**Phase 5 / 日常模式问题**：
- `apps/daemon/main.py` 只是最小 CLI daemon，主动消息只 `print`，没有真实托盘、桌宠、桌面通知或飞书/本地 UI 发送通道。
- `apps/tray/web_server.py` 只是 RuntimeStatus dataclass，不是 Web server；Tray 面板未真正接入。
- `CompanionContinuityService` 只有内存窗口和未回复计数，没有持久化、open threads、跨会话恢复。
- 未完成 30 分钟/24 小时 daemon 稳定性测试。

**修复顺序**：
1. P0：补真实感知，让云汐能真实读取当前时间、前台窗口、idle、基础系统状态，而不是测试友好空快照。
2. P0：清理 Runtime/MCP 私有字段访问和静默异常，补公开工具列表接口。
3. P0：把 HeartLakeUpdater 的关键词触发改为事件评估结构，至少先从硬编码词表迁移到可扩展 appraisal。
4. P1：让 Continuity 持久化，并引入 open threads。
5. P1：补真实 Tray/Web server 和 daemon 长时间稳定性测试。
6. P1：补 MCP 工具层缺口和用户确认通道。
7. P1：补 Memory 持久化、离线模型/初始化失败降级、学习周期调度。
8. P2：逐步替换裸 dict/Any 为 dataclass 或 TypedDict，减少规则模板化回复。

**当前决策**：
暂停继续扩展 Phase 5，不进入 Phase 6。先逐项修复上述问题，修复一项就补测试并更新本日志。

---

### [2026-04-15] Phase 4 边界补齐 + 正式进入 Phase 5

**决策**：
选择“补齐边界”而不是继续合并到 Runtime。原因：Phase 5 需要 daemon/tray 长期运行，如果 Presence、Continuity、HeartLakeUpdater 继续散落在 Runtime 内，Runtime 会演变成新的上帝类，不利于稳定性测试与后续维护。

**完成内容**：
- ✅ 新增 `core/cognition/heart_lake/updater.py`：`HeartLakeUpdater`，集中处理用户输入、感知 tick、互动完成后的情感更新
- ✅ 新增 `core/initiative/continuity.py`：`CompanionContinuityService`，维护最近 50 轮连续性窗口和未回复主动消息计数
- ✅ 新增 `core/resident/presence.py`：`YunxiPresence`，负责后台 tick 和主动消息回调，不直接生成内容
- ✅ `YunxiRuntime` 接入 HeartLakeUpdater / Continuity / Presence 所需边界：
  - 被动聊天后写入连续性
  - 主动消息写入连续性并计入未回复主动次数
  - 连续 3 次主动未回复后抑制第 4 次主动触发
- ✅ 新增 `apps/daemon/main.py`：日常模式 daemon 最小入口，支持 `--healthcheck`
- ✅ 新增 `apps/tray/web_server.py`：Runtime 状态快照适配，供 Tray/WebUI 使用
- ✅ 新增 Phase 5 最小闭环测试 `tests/integration/test_phase5_daily_mode.py`

**真实测试结果**：
- ✅ `python -m pytest -q tests\unit tests\domains\memory tests\integration\test_conversation_tester_baseline.py tests\integration\test_phase4_runtime.py tests\integration\test_phase5_daily_mode.py` → 60 passed
- ✅ `python -m pytest -q tests\integration\test_mcp_desktop.py` → 5 passed
- ✅ `python -m pytest -q tests\integration\test_phase4_real_llm_behavior.py tests\integration\test_end_to_end_llm.py` → 5 passed（真实 Moonshot/Kimi + MCPHub）
- ✅ `$env:PYTHONPATH='D:\yunxi3.0\src'; python -m apps.daemon.main --healthcheck --disable-tool-use` → 通过，输出 `daily_mode` 状态快照

**当前判断**：
Phase 4 设计边界已补齐，Phase 5 已正式启动并完成最小日常闭环：Runtime 可记录连续性，Presence 可驱动主动 tick，Tray 可读取状态，daemon 可构建真实 Runtime 并完成健康检查。

**下一步**：
1. 增加 daemon 30 分钟稳定性测试。
2. 将 `apps/tray/web_server.py` 从状态适配扩展为真实 HTTP 服务。
3. 扩大真实 LLM 日常模式回归用例，覆盖记忆闭环、连续性上下文和主动消息冷静期。

**阻塞**：无

---

### [2026-04-15] Phase 4 核心链路真实 LLM 行为验收通过

**完成内容**：
- ✅ 修复测试基础设施：`pytest.ini` 新增 `pythonpath = src`，避免手动设置 `PYTHONPATH`
- ✅ 修复感知测试注入：`PerceptionCoordinator.inject_snapshot()` 的注入快照现在能保留到下一次 `update()`，避免被默认采集覆盖
- ✅ 修复主动性链路：`YunxiExecutionEngine.respond()` 在 `user_input=""` 的主动触发场景不再尝试技能快速路径，避免未初始化技能库导致主动消息丢失
- ✅ 修复主动消息上下文重复写入：`YunxiRuntime.proactive_tick()` 不再在 Engine 已记录 assistant 消息后重复写入
- ✅ Runtime 初始化时自动将 `MCPHub.audit.memory_manager` 绑定到当前 `MemoryManager`，保证 MCP 审计具备写入经验池的通路
- ✅ 新增 `tests/unit/test_perception_coordinator.py`，覆盖感知注入 one-shot 行为
- ✅ 新增 `tests/integration/test_phase4_runtime.py`，覆盖感知进入 prompt、主动消息只记录一次
- ✅ 新增 `tests/integration/test_phase4_real_llm_behavior.py`，使用真实 Moonshot/Kimi 验证记忆、感知、情感和主动性是否真实影响生成

**真实测试结果**：
- ✅ `python -m pytest -q tests\unit tests\domains\memory tests\integration\test_conversation_tester_baseline.py tests\integration\test_phase4_runtime.py` → 50 passed
- ✅ `python -m pytest -q tests\integration\test_mcp_desktop.py` → 5 passed
- ✅ `python -m pytest -q tests\integration\test_phase4_real_llm_behavior.py` → 3 passed（真实 Moonshot/Kimi）
- ✅ `python -m pytest -q tests\integration\test_end_to_end_llm.py` → 2 passed（真实 Moonshot/Kimi + MCPHub + Desktop Server）

**遇到的问题与修复**：
1. 沙箱环境会拦截 HuggingFace 模型下载和 Windows named pipe，导致测试误报失败。已在非沙箱环境重跑并确认真实通过。
2. `ConversationTester` 原本默认初始化 `MemoryManager` 的语义模型，导致 Mock 对话测试依赖外部模型下载。已关闭测试 Runtime 的技能快速路径，Mock 对话测试不再依赖 HuggingFace。
3. 主动触发时 `user_input=""` 仍进入技能快速路径，导致 Engine 返回错误但不写入上下文。已改为只有非空用户输入才尝试技能快速路径。

**当前判断**：
Phase 3 基本实现并通过测试；Phase 4 的核心用户可见链路（情感、感知、记忆、主动性进入真实 LLM 生成）已经通过真实 LLM 验收。按原设计文档，`Presence`、`Continuity`、`HeartLakeUpdater` 的独立模块边界仍需补齐或明确合并到 Runtime 的设计决策。

**下一步**：
1. 补齐或正式调整 Phase 4 设计边界：Presence / Continuity / HeartLakeUpdater。
2. 进入 Phase 5 前，补日常模式 daemon/tray/runtime 全链路测试。

**阻塞**：无

---

### [2026-04-15] Phase 2 完成 + 真实 LLM 端到端验证通过

**完成内容**：
- ✅ 更新 `CODE_QUALITY_GUIDELINES.md`，新增"诚实报告问题、测试失败立即解决"和"云汐不是死板脚本执行程序"两条最高约束
- ✅ 新建 `src/core/types/message_types.py`，定义统一消息类型
- ✅ 实现 `src/core/execution/engine.py`：YunxiExecutionEngine、ConversationContext、EngineConfig、ExecutionResult
- ✅ 实现 `src/core/prompt_builder.py`：YunxiPromptBuilder
- ✅ 实现 `src/core/runtime.py`：YunxiRuntime
- ✅ 实现最小子系统 stub：MemoryManager、HeartLake、PerceptionCoordinator
- ✅ 实现 `tests/integration/conversation_tester.py`：YunxiConversationTester
- ✅ 新增 `src/core/llm/provider.py` + `adapter.py`：支持 OpenAI 兼容格式（Kimi/Moonshot、MiniMax）
- ✅ 编写并通过 `tests/unit/test_execution_engine.py`（4）
- ✅ 编写并通过 `tests/unit/test_prompt_builder.py`（7）
- ✅ 编写并通过 `tests/integration/test_conversation_tester_baseline.py`（5）
- ✅ 编写并通过 `tests/integration/test_end_to_end_llm.py`（2）——使用真实 Kimi API，验证 screenshot 和 clipboard 工具链
- ✅ 全量回归：30 个测试全部通过

**遇到的问题与修复**（诚实报告）：
1. **MiniMax Token Plan API 间歇性不稳定**：直接调用有时返回 `choices: null`。确认 API key 属于 `api.minimaxi.com`（中国站），但后端返回空结果频率高 → 切换至用户提供的 **Kimi (Moonshot) API** 进行端到端验证
2. **Adapter 未正确处理 OpenAI function calling 的消息格式**：
   - `AssistantMessage` 包含 `ToolUseBlockData` 时，adapter 原先丢弃了 tool_use 信息，导致 assistant message 的 content 为空，Moonshot 返回 400 `assistant message must not be empty` → 在 `Message` 中新增 `tool_calls` 字段，adapter 将 `ToolUseBlockData` 正确转换为 OpenAI tool_calls 格式
   - `ToolResultContentBlock` 被包装在 `UserMessage` 中，但 OpenAI 协议要求后续消息必须是 `role: tool` 且带有 `tool_call_id` → 修改 adapter，将 `ToolResultContentBlock` 列表拆分为多个 `role="tool"` 的 Message
3. **`RuntimeContext.mode` 值与 `SecurityManager` 不匹配**：`RuntimeContext` 默认 `mode="daily"`，但 `SecurityManager` 的 override/policy key 是 `"daily_mode"`，导致 tool override 未生效 → 将 `RuntimeContext` 和 `YunxiRuntime` 的 mode 统一为 `"daily_mode"`
4. **`MessageRole` Enum 缺少 `TOOL` 成员**：adapter 尝试创建 `MessageRole("tool")` 时抛出 `ValueError` → 添加 `TOOL = "tool"`

**当前状态**：Phase 2 全部交付物已实现并通过测试，**真实 LLM + MCPHub + Desktop Server 的端到端链路已跑通**。满足 MASTER_EXECUTION_PLAN 中 Phase 2 的所有验收标准。

**下一步**：进入 Phase 3 —— 记忆系统与终身学习。

**阻塞**：无

---

### [2026-04-15] Phase 2 执行引擎与对话验证框架完成

**完成内容**：
- ✅ 更新 `CODE_QUALITY_GUIDELINES.md`，新增"诚实报告问题、测试失败立即解决"和"云汐不是死板脚本执行程序"两条最高约束
- ✅ 新建 `src/core/types/message_types.py`，定义统一消息类型（UserMessage、AssistantMessage、ToolResultContentBlock 等）
- ✅ 实现 `src/core/execution/engine.py`：YunxiExecutionEngine、ConversationContext、EngineConfig、ExecutionResult
- ✅ 实现 `src/core/prompt_builder.py`：YunxiPromptBuilder（含 failure_hints section、感知增强、情感指引、工具列表）
- ✅ 实现 `src/core/runtime.py`：YunxiRuntime，统筹 Engine + PromptBuilder + 各子系统快照
- ✅ 实现最小子系统 stub：MemoryManager、HeartLake、PerceptionCoordinator，使 Phase 2 测试可独立运行
- ✅ 实现 `tests/integration/conversation_tester.py`：YunxiConversationTester（含 MockLLM、状态注入、剧本模式）
- ✅ 编写 `tests/unit/test_execution_engine.py`（4 用例通过）
- ✅ 编写 `tests/unit/test_prompt_builder.py`（7 用例通过）
- ✅ 编写 `tests/integration/test_conversation_tester_baseline.py`（5 用例通过）
- ✅ 全量回归：Phase 1 的 12 个测试 + Phase 2 的 16 个测试全部通过

**遇到的问题与修复**（诚实报告）：
1. `src/core/types/` 目录不存在 → 创建目录后再写文件
2. `prompt_builder.py` 中 `_build_identity_section` 的字符串包含未转义的中文引号 `"作"`，导致 `SyntaxError` → 改为单引号 `'作'`
3. `ConversationTester` 的 `MockLLM` 在 `__init__` 中预填充了一条默认回复，导致各测试添加的后续回复被排在后面，`llm.complete()` 始终返回默认回复而非测试期望的回复 → 移除默认回复，改由 `reset()` 同时清空 mock LLM 状态，并让每个测试显式添加所需回复

**当前状态**：Phase 2 全部交付物已实现并通过测试，满足 MASTER_EXECUTION_PLAN 中 Phase 2 的验收标准。

**下一步**：进入 Phase 3 —— 记忆系统与终身学习。

**阻塞**：无

---

### [2026-04-15] Phase 1 MCP 基础设施测试全部通过

**完成内容**：
- ✅ 实现 `core/mcp/client.py`（MCP stdio Client 封装，支持多 Server 连接、统一工具发现与调用）
- ✅ 实现 `core/mcp/hub.py`（MCPHub，整合安全校验、DAG 规划、执行与审计）
- ✅ 实现 `core/mcp/security.py`（SecurityManager，四级权限模型 + 模式策略 + 工具级覆盖）
- ✅ 实现 `core/mcp/audit_logger.py`（JSONL 审计日志，支持按日期分文件）
- ✅ 实现 `core/mcp/planner.py`（DAGPlanner 骨架，支持拓扑排序）
- ✅ 实现 `core/tools/desktop/uia_driver.py` 与 `visual_assertion.py`
- ✅ 实现 `core/mcp/servers/desktop_server.py`（FastMCP Desktop Server，支持截图、剪贴板、通知、UIA）
- ✅ 编写并跑通 `tests/unit/test_mcp_security.py`（7 passed）
- ✅ 编写并跑通 `tests/integration/test_mcp_desktop.py`（5 passed，包含真实 stdio server 启动与工具调用）
- ✅ 修复 pytest-asyncio 跨任务清理问题，创建 `pytest.ini` 统一配置

**当前状态**：Phase 1 P0 门槛（MCPHub 通过真实 clipboard 与 screenshot 测试）已达成。

**下一步**：
1. 完善 DAGPlanner 的循环检测与并行执行能力
2. 补充 Desktop Server 的更多边界测试
3. 进入 Phase 2：执行引擎与对话验证框架

**阻塞**：无

---

### [2026-04-14] Phase 0 完成 → 进入 Phase 1

**完成内容**：
- ✅ 初始化 yunxi3.0 完整目录结构（src/core/mcp/servers, src/core/tools/desktop, src/core/security, src/factory/templates 等）
- ✅ 创建 `requirements.txt`，包含 mcp, fastmcp, pyperclip, uiautomation, opencv-python, Pillow, sentence-transformers, scikit-learn, networkx, pystray, aiohttp 等核心依赖

**当前状态**：Phase 0 基建完成，正式进入 Phase 1 代码实现阶段。

**下一步**：按顺序实现：
1. `core/mcp/client.py` — MCP stdio Client 封装
2. `core/mcp/hub.py` — MCPHub
3. `core/mcp/security.py` — SecurityManager
4. `core/mcp/audit_logger.py` — AuditLogger
5. `core/mcp/planner.py` — DAGPlanner
6. `core/tools/desktop/uia_driver.py` — UIADriver
7. `core/tools/desktop/visual_assertion.py` — VisualAssertion
8. `core/mcp/servers/desktop_server.py` — Desktop MCP Server

**阻塞**：无

---

### [2026-04-14] Phase 0 - 设计文档全部完成

**完成内容**：
- ✅ 完成全部设计文档（MIGRATION_PLAN, TOOLS_REFACTOR, FACTORY_MODE, MEMORY_INTEGRATION, EXECUTION_ENGINE, PROMPT_BUILDER, MASTER_EXECUTION_PLAN）
- ✅ 完成 `CODE_QUALITY_GUIDELINES.md`
- ✅ 完成 `DEV_LOG.md`

**当前状态**：设计阶段全部结束，准备进入代码实现。

---

## 快速检查清单（每次对话开始时自答）

- [ ] 我已阅读了本文件的"当前快照"
- [ ] 我知道当前处于哪个 Phase
- [ ] 我知道下一步要做什么
- [ ] 如果有阻塞项，我已确认阻塞是否已解除

---

## 附录：Phase 定义速查

| Phase | 名称 | 核心交付物 |
|-------|------|-----------|
| Phase 0 | 基础准则与开发基建 | 设计文档、开发日志、目录结构、依赖配置 |
| Phase 1 | MCP 基础设施与工具层骨架 | MCP Client/Hub/Security/Audit、UIA 基础、Desktop Server |
| Phase 2 | 执行引擎与对话验证框架 | YunxiExecutionEngine、PromptBuilder、ConversationTester |
| Phase 3 | 记忆系统与终身学习 | SkillLibrary、PatternMiner、FailureReplay、Audit→Experience 联动 |
| Phase 4 | 情感系统修复与主动性重建 | HeartLakeUpdater、InitiativeEngine、Presence 简化 |
| Phase 5 | 日常模式端到端闭环 | YunxiRuntime、Daemon 适配、Tray 适配、全链路回归 |
| Phase 6 | 工厂模式核心引擎 | FactoryEngine、DAGScheduler、ClaudeWorker、Workspace |
| Phase 7 | 工厂监控与项目模板 | FactoryDashboard、PythonDesktopTemplate |
| Phase 8 | 工厂多 Worker 并行与桌宠验证 | 多 Worker 并行、Merge 冲突、yunxi-pet 完整执行、人工验收 |
| Phase 9 | 工程收尾与文档固化 | 20+ 端到端测试、24h 稳定性测试、文档更新 |

---

*最后更新：2026-04-14*  
*下次必读时间：每次新对话开始时*
