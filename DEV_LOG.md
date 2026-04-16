# 云汐 3.0 开发日志

> **用途**：记录当前开发状态、阻塞问题、重要决策和下一步计划。  
> **读取时机**：每次新对话开始时，必须先阅读本文件。  
> **更新原则**：只保留重要里程碑、真实验证结果、阻塞问题和阶段切换依据；删除低价值流水快照。  
> **核心验收标准**：云汐首先是住在电脑里的亲密伴侣；工具能力只能作为延伸，不能让云汐退化成高级脚本执行程序。

---

## [2026-04-16] 新增：日常模式仿真验收框架

**状态**：已完成首版搭建。该框架用于在进入工厂模式前，以真实日常使用方式验收云汐是否像“住在电脑里的女友”，而不是只验证函数调用是否成功。

### 新增/更新文件

- `docs/design/CONVERSATION_TESTER_DESIGN.md`：升级为 v2.0“日常模式仿真验收框架设计”，明确分层测试、真实 LLM、飞书 live、状态注入、行为检查和完成门槛。
- `tests/integration/daily_mode_scenario_tester.py`：新增 `DailyModeScenarioTester`，支持构建隔离 Runtime、注入记忆/情绪/感知/open thread、触发主动 tick、捕获通道消息、记录真实 LLM system prompt、执行行为检查。
- `tests/integration/test_daily_mode_scenario_tester.py`：新增框架自测，覆盖记忆注入、主动事件发送到 capture channel、吃醋状态变化、内部字段/工具化表达检查。
- `tests/integration/test_daily_mode_full_simulation_real_llm.py`：新增真实 LLM 日常仿真矩阵，覆盖本地 Ollama 和 Moonshot 两组，模拟记忆、情绪、陪伴、主动事件、open thread 和反工具化。
- `tests/integration/test_daily_mode_feishu_live.py`：新增飞书 live 主动发送测试，默认跳过，只有 `FEISHU_LIVE_TEST=1` 时真实发送消息。
- `pytest.ini`：新增 `feishu_live` marker。

### 已验证

- `python -m py_compile tests\integration\daily_mode_scenario_tester.py tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_daily_mode_full_simulation_real_llm.py tests\integration\test_daily_mode_feishu_live.py` -> passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py` -> 4 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py -m "not real_llm and not desktop_mcp"` -> 12 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k ollama` -> 2 passed（真实本地 Ollama）

### 重要发现

- 首次运行 Ollama 真实仿真时，框架错误地回退到了 `nomic-embed-text` embedding 模型，导致 `/api/chat` 400。已修复模型选择策略：当 `.env` 中配置的 `OLLAMA_MODEL` 不可用时，优先选择非 embedding 的聊天模型。
- 真实 Moonshot 组和飞书 live 组已经搭建，但未默认运行。Moonshot 需要可用外网/API；飞书 live 需要 `FEISHU_LIVE_TEST=1`，避免测试时误发消息。

### 后续必须补齐

1. 修复旧 `test_moonshot_cloud_matrix.py` 空事件库问题，并迁移到 `DailyModeScenarioTester`。
2. 修复 daemon stability 测试挂起问题，并复用新的 static perception provider。
3. 新增重启后记忆持久化测试，目前预计会暴露 `MemoryManager` 长期关系记忆不足。
4. 新增主动预算跨日重置测试，目前预计会暴露 `recent_proactive_count` 不按日期重置。
5. 新增飞书线程回调测试，目前预计会暴露 `asyncio.create_task()` 在线程中无 event loop 的问题。

---

## 当前总状态

**日期**：2026-04-16  
**阶段**：Phase 5 日常模式硬化中，尚不应进入 Phase 6 工厂模式。  
**本次动作**：清理旧开发日志，记录日常模式整体大审查结果。  

### 当前结论

- Phase 0-5 的骨架已经基本搭好：Runtime、PromptBuilder、LLMAdapter、MCPHub、Memory、HeartLake、Initiative、Presence、daemon、飞书通道、Ollama/Moonshot 接入均已有实现。
- yunxi2.0 的关键资产已经迁入一部分：人格 profile、用户关系 profile、生活事件库、三层主动事件系统、表达上下文、continuity/open_threads。
- 日常模式仍不能标记为完成。当前实现能跑出基础对话，但还没有达到“稳定常驻、真实主动、有长期关系记忆、入口可靠、真实 LLM 验收完整通过”的标准。
- 旧日志中“P0-E 全部完成”的表述已作废。真实云端矩阵和 daemon 稳定性测试当前没有通过。

### 进入工厂模式前的硬门槛

1. 日常模式真实 LLM 验收必须同时覆盖本地 Ollama 和云端 Moonshot，并实际跑通。
2. 飞书或其他真实入口必须能稳定接收用户消息、调用 Runtime、返回回复、发送主动消息。
3. Presence 长期运行不能卡死，daemon 稳定性测试必须可信。
4. 主动性预算、冷却、未回复克制必须按真实时间持久化，而不是进程内临时变量。
5. 记忆系统必须能沉淀“远”和云汐之间的重要事实，而不只是当前进程内列表。
6. 日常工具必须有真实确认通道，否则 daily_mode 下 WRITE/EXECUTE 工具不可用。
7. 云汐回复不能暴露工程错误、系统字段、工具失败模板或客服腔。

---

## 重要里程碑保留

### Phase 0：代码准则与项目骨架

- 已建立 `CODE_QUALITY_GUIDELINES.md`。
- 已建立 `src/`、`tests/`、`docs/design/`、`data/`、`logs/` 基础结构。
- 当前仍存在违反准则的问题：核心接口中 `Any` / `Dict` 过多，宽泛异常过多，部分同步阻塞 IO 混入异步链路。

### Phase 1：MCP 与桌面工具骨架

- 已实现 `MCPClient`、`MCPHub`、`DAGPlanner`、`SecurityManager`、`AuditLogger`。
- 已实现 Desktop MCP Server：截图、剪贴板、通知、启动应用、窗口聚焦、窗口最小化。
- 当前仍缺少 file/bash/browser MCP Server。
- 日常模式的安全确认链路未闭合：`ask` 当前只是变成工具错误，没有真实向用户确认。

### Phase 2：执行引擎与 PromptBuilder

- 已实现 `YunxiExecutionEngine`、`ConversationContext`、`ExecutionResult`。
- 已实现 `YunxiPromptBuilder`，能注入人格、关系、情感、感知、记忆、失败经验、连续性和工具列表。
- 当前问题：错误恢复仍模板化；Prompt 没有结构化压缩；工具失败会出现工程化回复。

### Phase 3：记忆与技能学习

- 已实现 `MemoryManager`、`ExperienceBuffer`、`PatternMiner`、`SkillDistiller`、`SkillLibrary`、`FailureReplay`、`ParamFiller`。
- 已接入本地 Ollama embedding provider 和 lexical fallback。
- 当前问题：长期关系记忆不完整，偏好/片段/承诺仍主要是进程内列表；技能蒸馏和参数填充仍偏正则。

### Phase 4：情感、主动性、人格资产迁移

- 已实现 HeartLake、HeartLakeUpdater、InitiativeEngine、ThreeLayerInitiativeEventSystem、ExpressionContextBuilder、ProactiveGenerationContextBuilder。
- 已迁入 persona profile、relationship profile、life events。
- 主动消息生成方向正确：最终文本由真实 LLM 生成，不恢复固定 fallback 文案。
- 当前问题：情感模型仍偏阈值机；关系等级固定；事件的 affect_delta 未真正影响 HeartLake；open_threads/proactive_cues 多数依赖手动写入。

### Phase 5：日常模式闭环

- 已实现 `YunxiRuntime`、daemon、Presence tick、Tray 状态快照适配、飞书通道草案。
- 已支持本地 Ollama 作为一等 LLM 后端。
- 当前问题：Tray/WebUI 不是真实服务；print 模式不是可交互入口；飞书通道存在高风险线程/异步问题；稳定性测试不可信。

---

## [2026-04-16] 日常模式整体大审查：重要问题清单

**审查目标**：在进入工厂模式前，按“住在电脑里的女友”“像人一样有感情、生动、活泼、长期陪伴”的设计初衷，重新检查当前所有核心实现。  

**审查范围**：

- `src/core/runtime.py`
- `src/core/prompt_builder.py`
- `src/core/persona/profile.py`
- `src/core/cognition/heart_lake/*`
- `src/core/cognition/initiative_engine/*`
- `src/core/initiative/*`
- `src/core/execution/engine.py`
- `src/core/llm/*`
- `src/core/mcp/*`
- `src/core/tools/desktop/*`
- `src/core/resident/presence.py`
- `src/domains/memory/*`
- `src/domains/perception/*`
- `src/apps/daemon/*`
- `src/apps/tray/*`
- `src/interfaces/feishu/*`
- `tests/unit/*`
- `tests/integration/*`
- `tests/domains/memory/*`
- `data/persona/*`
- `data/relationship/*`
- `data/initiative/*`

### 本次真实验证结果

- `python -m py_compile ...`：核心日常模式文件语法编译通过。
- `python -m pytest -q tests\unit tests\domains\memory tests\integration\test_conversation_tester_baseline.py tests\integration\test_phase5_daily_mode.py -m "not real_llm and not desktop_mcp"`：76 passed。
- `python -m pytest -q tests\integration\test_moonshot_cloud_matrix.py -m real_llm`：6 errors，全部卡在 fixture setup，未真正调用 Moonshot。
- `python -m pytest -q tests\integration\test_daemon_stability.py::test_stability_continuity_persistence -vv -s`：90 秒超时，测试未完成。
- 静态扫描：`src` 中约 129 处 `Any` / `Dict`，约 18 处宽泛异常，约 9 处同步阻塞或高风险调用模式（`requests` / `time.sleep` / `shell=True`）。

---

## P0：进入工厂模式前必须修复

### P0-01：Moonshot 云端真实 LLM 矩阵当前没有跑通

文件：`tests/integration/test_moonshot_cloud_matrix.py`

问题：
- fixture 把临时事件库写成 `[]`。
- `ThreeLayerInitiativeEventSystem` 明确拒绝空事件库。
- 6 个测试全部在 setup 阶段失败，没有实际调用 Moonshot，也没有验证云汐人格、主动性或记忆质量。

影响：
- “云端模型对照已完成”的结论不成立。
- 当前不能证明云汐在云端模型下符合日常模式设计。

修复要求：
- 使用真实 `data/initiative/life_events.json` 或写入最小有效事件库。
- 测试必须实际进入 `runtime.chat()` / `runtime.proactive_tick()`。
- 断言不能只查关键词，还要判断是否反工具化、是否符合人格、是否没有系统字段泄漏。

### P0-02：daemon 稳定性测试会挂住

文件：`tests/integration/test_daemon_stability.py`

问题：
- fixture 使用真实 `PerceptionCoordinator()`。
- `runtime.chat()` 会触发真实 Windows 感知读取，测试在当前环境下 90 秒未完成。

影响：
- “daemon 长时间稳定性测试完成”的结论不成立。
- 当前无法证明日常模式可长期常驻。

修复要求：
- 稳定性测试必须注入 static/mock perception provider。
- 真实桌面感知测试应单独放入 `desktop_mcp` 或专门 marker。
- daemon 稳定性需要至少覆盖短跑、长跑、主动 tick、连续 chat、异常恢复和资源释放。

### P0-03：飞书消息回调大概率无法在真实线程中调用 Runtime

文件：`src/interfaces/feishu/adapter.py`、`src/interfaces/feishu/websocket.py`

问题：
- `FeishuWebSocket` 在线程中运行 lark client。
- `FeishuAdapter.on_feishu_message()` 在同步回调里直接 `asyncio.create_task()`。
- WebSocket 线程通常没有正在运行的 event loop，会触发 `RuntimeError: no running event loop`。

影响：
- 飞书通道可能“能启动但收消息就失败”。
- 日常模式真实入口不可靠。

修复要求：
- daemon 创建 adapter 时必须传入主 asyncio loop。
- WebSocket 线程收到消息后用 `asyncio.run_coroutine_threadsafe()` 投递到主 loop。
- 增加真实或半真实回归测试，覆盖线程回调到 `runtime.chat()` 的链路。

### P0-04：Runtime 没有并发保护

文件：`src/core/runtime.py`、`src/core/execution/engine.py`、`src/core/initiative/continuity.py`

问题：
- 飞书用户消息、Presence 主动 tick、未来 Tray/WebUI 都可能并发调用 `runtime.chat()` / `runtime.proactive_tick()`。
- `ExecutionEngine.context`、`HeartLake`、`Continuity`、`MemoryManager` 都是可变状态，没有锁。

影响：
- 对话上下文可能交错。
- 主动消息和用户回复可能互相污染。
- 情感、未回复计数、open_threads 可能错乱。

修复要求：
- Runtime 层增加单入口异步锁或事件队列。
- 主动消息和用户消息必须统一排队。
- 增加并发测试：多条飞书消息 + Presence tick 同时发生时上下文仍一致。

### P0-05：主动预算不是“每日预算”，会永久耗尽

文件：`src/core/initiative/continuity.py`、`src/core/cognition/initiative_engine/engine.py`

问题：
- `recent_proactive_count` 只累加，不按日期重置。
- `InitiativeEngine` 用它判断 `daily_budget`。
- continuity 持久化后，一旦主动次数达到预算，可能长期不再主动。

影响：
- 云汐会从“有克制的主动陪伴”变成“沉默”。
- 这直接破坏日常模式的女友感。

修复要求：
- 记录主动计数所属日期。
- 跨天自动重置。
- 测试覆盖跨日预算、未回复克制、冷却、用户回复后恢复。

### P0-06：日常工具的安全确认链路没有闭合

文件：`src/core/mcp/security.py`、`src/core/mcp/hub.py`、`src/core/execution/engine.py`

问题：
- daily_mode 下 WRITE / EXECUTE 默认返回 `ask`。
- `MCPHub` 对 `ask` 的处理只是返回错误。
- 没有通过飞书、Tray、WebUI 或对话向用户发起确认。

影响：
- 云汐 prompt 里说“可以使用工具”，但实际调用会失败。
- 用户体验会变成“云汐想帮忙但总是说失败”。

修复要求：
- 设计统一确认协议：pending tool request。
- 飞书/Tray/WebUI 至少一个入口能完成确认。
- LLM 回复要自然表达“这个操作需要你点头”，不能暴露安全策略字段。

### P0-07：长期关系记忆还不是真正的长期记忆

文件：`src/domains/memory/manager.py`、`src/core/initiative/continuity.py`

问题：
- `record_preference()` / `record_episode()` / `record_promise()` 写入进程内列表。
- daemon 重启后这些记忆会丢失。
- `relationship_summary` / `emotional_summary` / `user_style_summary` 只支持手动更新，没有 LLM 总结写入链路。
- 普通聊天经验只进入 `ExperienceBuffer`，但没有转化为关系记忆。

影响：
- 云汐会有“失忆感”。
- 女友感依赖长期细节，而不是每轮 system prompt 静态设定。

修复要求：
- 将偏好、共同经历、承诺持久化。
- 增加聊天后异步记忆提取。
- 增加关系摘要和情绪摘要的周期性 LLM 更新。
- 测试必须覆盖重启后仍记得用户事实。

### P0-08：飞书发送链路在 async 函数里使用同步 requests

文件：`src/interfaces/feishu/client.py`、`src/interfaces/feishu/adapter.py`

问题：
- `FeishuClient` 使用同步 `requests`。
- `FeishuAdapter.handle_message()` / `send_proactive_message()` 是 async，但内部直接阻塞发送。

影响：
- 飞书 API 慢或网络抖动时会阻塞主事件循环。
- Presence tick、用户消息和未来 UI 入口都会被拖慢。

修复要求：
- 改为 `httpx.AsyncClient` 或 `asyncio.to_thread()` 包装同步请求。
- 增加超时、重试和失败降级。
- 主动消息失败不能影响 Runtime 主循环。

### P0-09：FeishuWebSocket 停止逻辑不完整

文件：`src/interfaces/feishu/websocket.py`

问题：
- `stop()` 只设置 `_running = False`。
- 没有停止 lark client。
- 没有 join 线程。

影响：
- daemon 退出时可能残留后台线程或连接。
- 长期运行/重启会不稳定。

修复要求：
- 明确 lark client 的关闭 API。
- stop 时关闭 client、等待线程退出、超时后记录警告。

### P0-10：错误回复破坏人格

文件：`src/core/execution/engine.py`

问题：
- LLM 或工具异常时返回 `[云汐这里出了点小问题：...]`、`[工具执行遇到问题，请换个方式说吧]`。
- 这类括号化工程提示不符合“住在电脑里的女友”。

影响：
- 一旦出错，云汐立刻变成程序错误提示器。

修复要求：
- 对用户可见错误必须走人格化表达。
- 技术细节进入日志，不直接进入用户回复。
- 测试覆盖 LLM 异常、工具异常、安全 ask、未知工具。

---

## P1：日常模式质量问题

### P1-01：HeartLake 仍偏阈值状态机

文件：`src/core/cognition/heart_lake/core.py`、`src/core/cognition/heart_lake/updater.py`

问题：
- 情感更新主要由 idle、app、hour、关键词/正则触发。
- `_JealousyAppraisal` 比原先更集中，但仍是模式匹配，不是语义 appraisal。
- `AppraisalRule.DEFAULT_RULES` 没有真正启用。
- `relationship_level` 固定为 4，没有升级/降级/仪式感。

影响：
- 云汐的情感不够“像人”，更像数值状态机。

修复方向：
- 引入 LLM 或轻量语义分类器做对话 appraisal。
- 引入情感惯性、恢复曲线、关系仪式和长期关系事件。
- 将事件库 `affect_delta` 真实写入 HeartLake。

### P1-02：主动事件只作为 prompt 素材，未真正影响情绪

文件：`src/core/initiative/event_system.py`、`src/core/runtime.py`

问题：
- `InitiativeEvent.affect_delta` 被加载，但没有应用到 HeartLake。
- 事件选择不会改变云汐“自己的心情”。

影响：
- 事件库更像话题素材库，不像云汐自己的生活体验。

修复方向：
- 事件被选中后将 affect_delta 写入 HeartLake。
- 将事件记入 continuity，避免主动消息没有生活连续性。

### P1-03：open_threads 和 proactive_cues 缺少自动生成

文件：`src/core/initiative/continuity.py`、`src/core/runtime.py`

问题：
- `add_open_thread()`、`add_proactive_cue()` 已有，但普通对话不会自动抽取未完成话题。
- 用户说“明天提醒我”“下次再聊”之类内容不会自动进入主动线索。

影响：
- 云汐不会真正“记挂着上次没聊完的事”。

修复方向：
- chat 后增加 LLM/规则混合抽取：承诺、未完成话题、用户状态、主动线索。
- 测试覆盖 open thread 自动生成和主动延续。

### P1-04：技能快速路径绕过 LLM，容易退回工具助手

文件：`src/core/execution/engine.py`

问题：
- 匹配到技能后直接执行工具并返回固定变体。
- 回复比以前不再单一句，但仍不是根据当前情绪、关系、上下文生成。

影响：
- 高频工具使用时，云汐会像脚本执行器。

修复方向：
- 工具执行结果应回到 LLM 做最终自然表达，或至少把 HeartLake/relationship/context 纳入回复选择。
- 快速路径只负责执行，不负责最终人格化表达。

### P1-05：PromptBuilder 只拼接，不压缩

文件：`src/core/prompt_builder.py`

问题：
- memory、continuity、tools、event context 都直接拼接。
- 没有 token 预算、优先级、结构化压缩或过期策略。

影响：
- 长期运行后 prompt 会膨胀或截断关键信息。
- 重要关系记忆可能被普通工具日志挤掉。

修复方向：
- 建立 prompt section budget。
- 关系事实、当前情绪、未完成话题优先级高于工具经验。
- 增加结构化压缩测试。

### P1-06：Perception 真实感知能力远低于设计目标

文件：`src/domains/perception/coordinator.py`

问题：
- 当前只采集时间、前台窗口、idle、CPU。
- 设计中的桌面文件、最近文件、天气、网络、剪贴板、窗口内容、应用语义都未实现。
- `fetch()` 是同步调用，缺少总超时。

影响：
- 云汐“住在电脑里”的感知太薄。
- 真实桌面读取异常可能阻塞聊天。

修复方向：
- 感知 provider 分层：快速基础感知、慢速外部感知、可选隐私感知。
- 每类感知都要有超时和降级。

### P1-07：Tray/WebUI 还不是日常入口

文件：`src/apps/tray/web_server.py`

问题：
- 当前只有 `RuntimeStatus` 和 `build_runtime_status()`。
- 没有真实托盘图标、Web server、聊天入口、确认入口、主动消息展示。

影响：
- 非飞书模式下 daemon 只能打印主动消息，不能完整互动。

修复方向：
- 至少实现一个本地 WebUI 或系统托盘入口。
- 支持 chat、主动消息流、工具确认、状态查看。

### P1-08：LLM provider 缺少生产级重试和错误分层

文件：`src/core/llm/provider.py`、`src/core/llm/adapter.py`

问题：
- `LLMConfig.max_retries` 没有实际使用。
- HTTP 错误直接 `raise_for_status()`。
- tool arguments JSON 解析失败会冒到 engine 变成泛化错误。
- `stream()` 没有处理 Ollama 原生流式协议。

影响：
- 网络波动时日常模式容易中断。
- 错误不可区分：配置错、限流、模型不可用、输出非法都会混在一起。

修复方向：
- 增加 provider 级错误类型。
- 使用 max_retries、指数退避、可观测日志。
- Ollama stream 单独实现或明确禁用。

### P1-09：MCPClient 缺少调用超时

文件：`src/core/mcp/client.py`、`src/core/mcp/hub.py`

问题：
- server connect、tool call 没有统一 timeout。
- 未知工具在 `MCPHub` 中直接 raise，可能绕过审计。

影响：
- 单个工具卡住会拖住整轮对话。
- 失败经验不完整，后续学习无法复盘。

修复方向：
- 对 connect/list_tools/call_tool 增加 timeout。
- 未知工具也应转成结构化 ToolChainResult 并写审计。

### P1-10：桌面工具有安全和准确性缺口

文件：`src/core/tools/desktop/uia_driver.py`、`src/core/mcp/servers/desktop_server.py`

问题：
- `UIADriver.launch_application()` 找不到 PATH 时使用 `shell=True`。
- `screenshot_capture(save_path)` 没有限制保存路径。
- `app_launch_ui()` 只靠屏幕像素变化判断成功，可能重复启动多个实例。
- `clipboard_read()` 可能把敏感剪贴板内容直接交给 LLM。

影响：
- 安全边界不符合代码准则。
- 桌面操作成功率和隐私控制不足。

修复方向：
- 应用启动改为 allowlist 或显式确认。
- 截图路径限制到项目/用户授权目录。
- 剪贴板读取加入隐私确认或脱敏策略。
- app 启动增加窗口检测。

### P1-11：飞书通道缺少真实消息边界

文件：`src/interfaces/feishu/*`

问题：
- 没有明确忽略机器人自己发送的消息。
- 消息去重集合超过 2000 后整表清空，可能允许旧消息重复。
- `transport` 字段未使用。
- `proactive_callback` 参数未实际参与逻辑。
- 可选飞书模块在 daemon 顶部导入，导致不用飞书时也依赖 `lark-oapi`。

影响：
- 长期运行可能出现重复消息、循环消息或不必要依赖失败。

修复方向：
- 增加 self-message filter。
- 用 TTL/LRU 去重。
- 飞书相关导入延迟到 `--feishu-enable` 分支。

### P1-12：Memory/SkillLibrary 资源生命周期不完整

文件：`src/domains/memory/manager.py`、`src/domains/memory/skills/pattern_miner.py`、`src/domains/memory/skills/skill_library.py`、`src/apps/daemon/main.py`

问题：
- `PatternMiner.close()`、`SkillLibrary.close()` 存在，但 `MemoryManager` 没有统一 close。
- `close_runtime()` 没有关闭 memory embedding 资源。
- `OllamaSkillEmbedder.initialize()` 创建 async client，但 `encode_sync()` 使用新的同步 client，async client 实际闲置。
- `SkillLibrary.retrieve()` 中 Ollama embedding 同步请求会阻塞事件循环。

影响：
- 长期 daemon 可能资源泄漏或被 embedding 请求卡住。

修复方向：
- `MemoryManager.close()` 统一释放所有资源。
- Ollama embedding 统一 async 化。
- daemon close_runtime 必须关闭 memory。

---

## P2：工程质量和测试覆盖问题

### P2-01：类型系统仍不符合准则

问题：
- `src` 中约 129 处 `Any` / `Dict`。
- 核心接口如 Engine、MCP、Memory、LLM Adapter 仍依赖 duck typing。

影响：
- 工厂模式会放大接口不稳定问题。

修复方向：
- 用 dataclass / Protocol / TypedDict 替换核心裸 dict。
- 先处理 Runtime、Engine、MCPHub、Memory、LLMResponse、ToolResult。

### P2-02：宽泛异常仍偏多

问题：
- `src` 中约 18 处 `except Exception` 或等价宽泛捕获。
- 部分捕获只返回字符串，缺少错误类型和上下文。

影响：
- 真实问题容易被吞掉。
- 用户可见回复和日志不可追踪。

修复方向：
- 定义 RuntimeError、ToolError、ProviderError、PerceptionError、FeishuError。
- 底层记录技术上下文，上层转换成人格化回复。

### P2-03：测试仍有“浅验收”问题

问题：
- Moonshot matrix 当前没跑到 LLM。
- daemon stability 用 MockLLM 且挂在真实感知。
- 真实 LLM 测试主要靠关键词断言，不能充分判断“女友感”。
- 飞书没有真实收发链路测试。
- Ollama embedding 没有 live 测试。
- 没有并发测试、跨日预算测试、重启后记忆测试、工具确认测试。

修复方向：
- 增加 LLM-as-judge 或结构化评价器，判断是否客服腔、是否工具化、是否关系连续。
- 将真实 LLM 测试分成本地 Ollama、云端 Moonshot、入口通道、桌面工具四组。
- 每组失败必须阻止进入下一阶段。

### P2-04：用户关系资料文件可读性差

文件：`data/relationship/user_profile.md`

问题：
- 文件内容大量使用 `\uXXXX` 转义，程序能解码，但人类维护体验差。

影响：
- 用户后续手动修改关系资料不方便。

修复方向：
- 改成真实中文 Markdown，并保留加载兼容。

### P2-05：healthcheck 太浅

文件：`src/apps/daemon/main.py`

问题：
- healthcheck 只构建 Runtime 和状态快照。
- 不验证 LLM 可用性、主动 tick、飞书配置、工具确认通道、memory close。

影响：
- healthcheck passed 不代表日常模式能真实工作。

修复方向：
- 增加 `--healthcheck-deep`。
- 覆盖 LLM ping、memory init/close、event library、continuity read/write、optional feishu config。

---

## 日常模式完善规划

本规划把上方 P0/P1/P2 问题整理成可执行依赖链。原则是：先恢复验收可信度，再修入口和并发，再修长期陪伴能力，最后补工具确认、WebUI 和感知增强。每一阶段完成后必须进入对应的仿真验证层，验证通过后才进入下一阶段。

### 阶段 0：冻结目标与验收口径

目标：确保后续所有修复都围绕“住在电脑里的亲密伴侣”展开，而不是把云汐推回工具助手。

必须保持：
- `DailyModeScenarioTester` 作为日常模式验收主框架。
- `DEV_LOG.md` 只记录真实通过的验证结果，不再保留“预计完成”“理论完成”结论。
- Phase 6 工厂模式继续冻结。

通过标准：
- `tests/integration/test_daily_mode_scenario_tester.py` 通过。
- 行为检查器能识别内部字段泄露、工具化表达和过长输出。

完成后进入：阶段 1。

### 阶段 1：恢复验收可信度

先修问题：
- P0-01：修复 `test_moonshot_cloud_matrix.py` 空事件库，或直接迁移到 `DailyModeScenarioTester`。
- P0-02：修复 `test_daemon_stability.py` 真实感知导致的挂起，改用 static/mock perception provider。
- P2-03：把真实 LLM 测试从浅关键词验收升级为行为验收，至少检查反工具化、人格、系统字段不泄露。

原因：
- 如果 Moonshot 矩阵没有真正跑到 LLM，云端模型质量无法判断。
- 如果 daemon 稳定性测试会挂住，后续所有入口和常驻能力都没有可信基线。

必须验证：
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py`
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k ollama`
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k moonshot`
- `python -m pytest -q tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"`

通过后可以进入：
- 日常模式仿真验证 Layer 2（本地 Ollama + Moonshot）。
- 阶段 2 的入口、飞书和并发修复。

未通过时禁止：
- 宣布日常模式完成。
- 新增工厂模式代码。
- 用 mock 测试替代真实 LLM 结论。

### 阶段 2：修 Runtime 单入口、飞书通道和常驻稳定性

先修问题：
- P0-03：飞书 WebSocket 线程回调必须投递到主 asyncio loop。
- P0-04：Runtime 增加单入口异步锁或事件队列，串行化 `chat()` / `proactive_tick()`。
- P0-08：飞书发送链路改 async，或用 `asyncio.to_thread()` 包裹同步 `requests`。
- P0-09：`FeishuWebSocket.stop()` 完成 client 停止、线程 join 和超时告警。
- P1-11：增加 self-message filter、TTL/LRU 去重，飞书导入延迟到 `--feishu-enable` 分支。

原因：
- 飞书是当前最接近日常真实入口的通道；如果收消息、回消息、主动消息任一环不可靠，日常模式仍只能算内部 demo。
- Runtime 内部状态大量可变，没有并发保护会污染情绪、连续性和上下文。

必须新增/修复测试：
- 飞书线程回调测试：模拟 WebSocket 线程调用 `on_feishu_message()`，确认能安全进入主 loop 并调用 `runtime.chat()`。
- Runtime 并发测试：多条用户消息 + proactive tick 同时发生时，continuity 顺序一致，未回复计数不乱。
- 飞书发送失败降级测试：发送失败不能阻塞 Presence 主循环。

必须验证：
- 阶段 1 的 Layer 2 真实 LLM 仿真仍通过。
- 飞书桥接测试通过。
- 手动开启时 `FEISHU_LIVE_TEST=1` 的飞书 live 主动发送通过。

通过后可以进入：
- 日常模式仿真验证 Layer 3（真实通道验收）。
- 阶段 3 的主动性、长期记忆和跨日模拟。

### 阶段 3：修主动性、长期关系记忆和连续性沉淀

先修问题：
- P0-05：`recent_proactive_count` 改为按日期统计，跨天自动重置。
- P0-07：偏好、共同经历、承诺从进程内列表改为持久化关系记忆。
- P1-02：主动事件被选中后，将 `affect_delta` 应用到 HeartLake，并写入 continuity。
- P1-03：普通聊天后自动抽取 open_threads、proactive_cues、偏好和承诺。
- P1-12：补 `MemoryManager.close()`，统一关闭 PatternMiner / SkillLibrary / embedding 资源。

原因：
- 女友感依赖长期细节和“记挂着上次没聊完的事”，不能只靠静态 persona prompt。
- 主动预算不跨日重置会让云汐长期沉默；记忆不持久化会造成失忆感。

必须新增/修复测试：
- 重启后记忆测试：写入偏好/承诺，关闭并重建 Runtime 后仍能召回。
- 跨日预算测试：当天预算耗尽后，模拟第二天，主动预算恢复。
- open thread 自动生成测试：用户说“明天提醒我”“下次再聊”后进入主动线索。
- 事件情绪影响测试：选中事件后 HeartLake 状态出现对应变化。

必须验证：
- Layer 2 真实 LLM 仿真仍通过。
- Layer 3 飞书通道仍通过。
- 新增长程日常模拟 Layer 4：模拟一天或多天的早晨、工作、深夜、离开、回来、未回复克制、跨日预算和重启记忆。

通过后可以进入：
- 阶段 4 的工具确认和错误人格化。

### 阶段 4：修日常工具确认和用户可见错误人格化

先修问题：
- P0-06：实现统一 pending tool confirmation 协议。
- P0-10：所有用户可见错误改为云汐人格化表达，技术细节只进日志。
- P1-04：技能快速路径只负责执行，工具结果回到 LLM 做最终自然表达，或纳入 HeartLake/relationship/context 生成。
- P1-08：LLM provider 增加错误类型、`max_retries`、退避重试和可观测日志。
- P1-09：MCP connect/list_tools/call_tool 增加 timeout；未知工具也转为结构化 ToolChainResult 并审计。
- P1-10：桌面工具补安全边界：截图路径限制、应用启动 allowlist 或确认、剪贴板读取隐私策略。

原因：
- daily_mode 下 WRITE/EXECUTE 工具当前会变成安全错误，用户体验是“云汐想帮忙但总失败”。
- 出错时不能暴露 `[工具执行遇到问题]` 或 `[云汐这里出了点小问题]` 这类工程模板。

必须新增/修复测试：
- 工具确认测试：写剪贴板/启动应用进入 pending confirmation，经飞书或本地入口确认后继续执行。
- 错误人格化测试：LLM 异常、工具异常、安全 ask、未知工具都返回自然表达。
- provider 重试测试：临时网络错误触发重试，最终失败时错误类型可区分。

必须验证：
- Layer 2/3/4 继续通过。
- 工具确认链路至少有一个真实入口能闭合。

通过后可以进入：
- 阶段 5 的 WebUI/Tray 和感知增强。

### 阶段 5：补真实日常入口、Tray/WebUI 和分层感知

先修问题：
- P1-06：Perception provider 分层，基础感知、慢速外部感知、可选隐私感知分别带 timeout 和降级。
- P1-07：实现真实本地 WebUI 或系统托盘入口，支持 chat、主动消息展示、工具确认、状态查看。
- P2-05：增加 `--healthcheck-deep`，覆盖 LLM ping、memory init/close、event library、continuity read/write、optional feishu config。
- P2-04：把 `data/relationship/user_profile.md` 改成真实中文 Markdown，保留转义加载兼容。
- P2-01 / P2-02：逐步用 dataclass / Protocol / TypedDict 替换核心裸 `Any` / `Dict`，并减少宽泛异常。

原因：
- 飞书不是唯一入口；本地入口缺失会导致 daemon 在非飞书模式下只能 print。
- 感知太薄会削弱“住在电脑里”的真实感，但感知增强必须先有超时、隐私和降级边界。

必须新增/修复测试：
- WebUI/Tray smoke test：能发 chat、显示主动消息、提交工具确认。
- deep healthcheck 测试：能发现 LLM、memory、event library、continuity 和飞书配置问题。
- 感知 timeout 测试：慢 provider 不阻塞整轮聊天。

必须验证：
- 日常模式全量仿真矩阵通过。
- daemon 短跑/长跑稳定性通过。
- 至少一个真实入口完成 chat + 主动消息 + 工具确认。

通过后可以进入：
- 日常模式完成候选验收。

### 日常模式完成候选验收门槛

只有同时满足以下条件，才允许把 Phase 5 标记为完成，并讨论是否进入 Phase 6：

1. 本地 Ollama 与 Moonshot 的 Layer 2 日常仿真全部通过。
2. Layer 3 飞书 live 主动发送在手动开启时通过。
3. Layer 4 长程日常模拟通过，覆盖未回复克制、跨日预算、重启记忆。
4. daemon stability 不挂起，短跑和长跑结果可信。
5. Runtime 并发测试通过。
6. 飞书真实入口能稳定收消息、调用 Runtime、回消息、发送主动消息。
7. 工具确认链路闭合，WRITE/EXECUTE 不再直接变成安全错误。
8. 用户可见错误不暴露工程模板、内部字段或系统栈信息。
9. 长期关系记忆重启后不丢失。
10. `DEV_LOG.md` 记录了真实命令、模型、通过结果和剩余风险。

---

## 当前禁止事项

- 禁止直接进入 Phase 6 工厂模式。
- 禁止再次把 P0-E 标记为完成，直到真实 LLM 矩阵和 daemon 稳定性通过。
- 禁止用只跑函数是否成功的测试替代真实 LLM 行为验收。
- 禁止为了推进进度把云汐写成工具调度器、脚本执行器或客服助手。
- 禁止新增大功能前继续堆叠未关闭的 Runtime/入口/记忆/主动性技术债。
