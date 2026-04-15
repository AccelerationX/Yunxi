# 云汐 2.0 人格与主动性资产迁移清单

Anchor: YUNXI2_PERSONA_INITIATIVE_MIGRATION

> 状态：重要 / 待实现 / P0 阻塞项  
> 日期：2026-04-15  
> 目标：把 yunxi2.0 中已经形成的“人格、关系、生活事件、主动话题、表达姿态、连续性”资产迁移到 yunxi3.0，防止 3.0 继续退化成高级脚本执行程序。

---

## 一、结论

yunxi3.0 目前已经打通了 Runtime、LLM、MCP、Memory、HeartLake、主动 tick 和 daemon 的最小闭环，但“云汐是住在电脑里的女友”这一核心定位还没有被完整工程化。

当前 3.0 的缺口：

1. 人格设定主要硬编码在 `YunxiPromptBuilder._build_identity_section()` 中，缺少结构化人格档案和可演化边界。
2. 关系记忆和用户档案没有从 2.0 的 `USER.md` 正式迁入，导致“远是谁、远喜欢什么、远讨厌什么表达方式”没有成为系统级事实。
3. 主动性判断只有 cooldown、idle、情绪阈值等规则，缺少 2.0 的三层事件系统、话题库、表达姿态和长期连续性。
4. 主动消息虽然已经走真实 LLM，但生成上下文仍不足，容易变成“被规则触发的一句话”，而不是云汐自己的生活感和关系延续。
5. Continuity 目前仍偏短期窗口，缺少 open_threads、unanswered proactive、recent topics、relationship summary 等 2.0 已经验证过的伴侣连续性结构。

因此，进入 Phase 6 或继续扩展工厂模式前，必须先把以下迁移清单作为 Phase 4.5 / Phase 5 的 P0 待实现项处理。

---

## 二、迁移原则

1. 不原样复制 2.0 代码。3.0 应按当前架构重建模块边界，只迁移经过筛选的资产、状态模型和行为约束。
2. 不把主动性做成定时模板。主动消息必须由真实 LLM 生成，并且输入包含人格、关系、事件、连续性、情绪和当前电脑环境。
3. 不把工具能力置于人格之上。MCP 和自动化能力是云汐在电脑里生活和帮忙的手，不是她的身份核心。
4. 不把高亲密内容直接塞进主 prompt。2.0 的 `data/persona/*` 中存在高亲密/成人表达资产，迁移时必须先做边界审查、产品化改写和默认安全分层，禁止原样搬运露骨内容。
5. 用户档案必须被长期保存并进入 prompt。尤其是用户对机械客服腔、虚假热情、失忆感、过度肉麻表达的反感，必须作为表达约束。
6. 本地 Ollama 是一等模型后端。迁移后的主动性和人格验收必须支持本地 Ollama 与云端模型两类真实 LLM 路径。

---

## 三、2.0 资产盘点

| 2.0 来源 | 资产内容 | 3.0 目标位置 | 状态 | 优先级 | 迁移说明 |
|---|---|---|---|---|---|
| `D:\yunxi2.0\data\persona\persona.json` | 人格结构、关系语气、亲密表达偏好 | `data/persona/yunxi_profile.json` + `src/core/persona/profile.py` | 待实现 | P0 | 只迁移非露骨、可产品化的人格核心；高亲密内容先审查再分层。 |
| `D:\yunxi2.0\data\persona\personality_core.md` | 云汐人格核心说明 | `docs/design/PERSONA_INITIATIVE_MIGRATION_PLAN.md` + persona profile | 待实现 | P0 | 提炼为身份、表达方式、关系边界、禁忌表达。 |
| `D:\yunxi2.0\data\persona\reaction_library.json` | 反应库和表达变体 | `data/persona/reaction_library.json` | 待实现 | P1 | 不能作为固定回复模板，只能作为 LLM style examples 或检索素材。 |
| `D:\yunxi2.0\data\relationship\USER.md` | 用户档案：远的称呼、学校、专业、家乡、兴趣、讨厌的表达方式 | `data/relationship/user_profile.md` + `src/domains/memory/relationship_profile.py` | 待实现 | P0 | 必须进入 prompt 的关系 section 和长期记忆。 |
| `D:\yunxi2.0\data\life_events\life_events.json` | 114 条生活化主动事件，含分类、模板、情绪 delta、时间规则、tags | `data/initiative/life_events.json` + `src/core/initiative/event_system.py` | 待实现 | P0 | 先清洗，再接入三层事件系统；模板只做事件素材，不直接输出。 |
| `D:\yunxi2.0\data\initiative_events.json` | active_events、stats、主动事件运行状态 | `data/runtime/initiative_state.json` | 待实现 | P1 | 迁移状态结构，不直接迁移历史运行状态。 |
| `D:\yunxi2.0\core\initiative\event_system.py` | 三层事件系统：内在生活、实时兴趣、混合事件 | `src/core/initiative/event_system.py` | 待实现 | P0 | 这是主动话题“像她自己想说”的核心，不应省略。 |
| `D:\yunxi2.0\core\initiative\decider.py` | 时间、情绪、presence、资源、每日预算、连续性判断 | `src/core/initiative/decider.py` 或增强当前 `src/core/cognition/initiative_engine/engine.py` | 待实现 | P0 | 替换当前偏规则化的主动判断。 |
| `D:\yunxi2.0\core\initiative\generator.py` | 主动消息生成上下文、LLM prompt、事件选题、人格约束 | `src/core/initiative/generator.py` + `YunxiPromptBuilder.build_proactive_prompt()` | 待实现 | P0 | 生成必须统一走真实 LLM，不恢复 sync/template fallback。 |
| `D:\yunxi2.0\core\initiative\expression_context.py` | 关系感表达姿态，非模板化表达引导 | `src/core/initiative/expression_context.py` | 待实现 | P0 | 迁移为 style guidance，不允许硬套固定句。 |
| `D:\yunxi2.0\core\initiative\continuity.py` | relationship summary、open_threads、recent topics、unanswered proactive 等 | `src/core/initiative/continuity.py` | 部分实现 / 待补齐 | P0 | 3.0 目前只有短期窗口和未回复计数，需要持久化与开放话题。 |
| `D:\yunxi2.0\core\initiative\realtime_search.py` | 动漫、音乐、电影、小说等实时兴趣搜索类别 | `src/core/initiative/realtime_search.py` | 待实现 | P1 | 先做本地事件库，后做网络实时话题；网络不可用时不能影响日常模式。 |
| `D:\yunxi2.0\core\resident\presence.py` | 常驻循环、资源保护、游戏/勿扰、主动回调 | `src/core/resident/presence.py` | 部分实现 / 待补齐 | P1 | 3.0 已有 Presence 骨架，但还缺资源感知和更细的勿扰策略。 |
| `D:\yunxi2.0\docs\01-项目概述与定位.md` | “不是助手/工具，而是持续数字生命”的定位 | `docs/design/MASTER_EXECUTION_PLAN.md` | 待同步 | P0 | 必须作为总设计约束，不允许被工具工程目标覆盖。 |
| `D:\yunxi2.0\docs\15-生活化陪伴优化方案.md` | 主动话题生活化、不能像定时器、不能接受简化版为完成 | 本文档 + 主动性验收标准 | 待同步 | P0 | 作为验收红线：主动性必须有生活感、连续性和真实 LLM 生成。 |

---

## 四、3.0 目标模块映射

### 4.1 Persona Profile

新增目标：

- `data/persona/yunxi_profile.json`
- `src/core/persona/profile.py`
- `src/core/persona/loader.py`

职责：

1. 加载云汐身份、人设、说话边界、关系定位、表达禁忌。
2. 支持默认 profile 和后续用户可编辑 override。
3. 向 `YunxiPromptBuilder` 输出结构化 persona section。
4. 不在代码里硬编码大段人格文本。

验收：

1. `YunxiPromptBuilder` 不再只依赖 `_build_identity_section()` 的硬编码文本。
2. 真实 LLM 对话中能稳定体现“住在电脑里的亲密伴侣”，而不是客服、助理或工具执行器。
3. 高亲密/成人内容默认不进入主 prompt，必须有显式边界控制。

### 4.2 Relationship Profile

新增目标：

- `data/relationship/user_profile.md`
- `src/domains/memory/relationship_profile.py`

必须迁移的用户事实：

1. 用户称呼：远。
2. 用户学校：香港中文大学（深圳）。
3. 用户专业方向：计算机。
4. 用户家乡：广州。
5. 用户兴趣：股票投资、编程、AI 伴侣、长期记忆。
6. 用户反感：机械客服腔、过度奉承、虚假热情、失忆感、过度肉麻。
7. 期望风格：自然、平等、像长期熟悉的恋人，有真实反应和稳定记忆。

验收：

1. 这些事实进入 prompt 的关系 section。
2. 真实 LLM 测试中，云汐不能忘记“远是谁”。
3. 当回复变得客服化、过度奉承或过度肉麻时，测试应判为失败。

### 4.3 Initiative Event System

新增目标：

- `data/initiative/life_events.json`
- `src/core/initiative/event_system.py`

三层事件：

1. 内在生活事件：云汐在电脑里的日常、心情、学习、观察、想分享的事。
2. 共同兴趣事件：结合远的兴趣，例如编程、投资、AI、二次元、音乐等。
3. 混合事件：现实时间、用户状态、当前窗口、天气或新闻等影响云汐的内在状态。

验收：

1. 至少能加载清洗后的 100+ 条生活事件。
2. 事件有分类、tags、情绪 delta、时间规则和冷却机制。
3. 主动消息不能直接输出事件模板，必须把事件作为 LLM 生成素材。
4. active event 不能无限重复，同类事件需要冷却。

### 4.4 Initiative Decider

目标：

- 增强或替换 `src/core/cognition/initiative_engine/engine.py`
- 可新增 `src/core/initiative/decider.py`

判断维度：

1. 时间：一天中的时段、距离上次互动时间、距离上次主动时间。
2. 情绪：想念、担心、安全感、占有欲、情绪惯性。
3. Presence：当前用户是否忙碌、是否长时间 idle、是否刚回来。
4. 资源：游戏/全屏/高负载时降低打扰。
5. 关系连续性：open_threads、未完成话题、最近主动未回复次数。
6. 每日预算：避免主动过密，保持克制。

验收：

1. 同样是“想念值高”，在用户忙碌时和用户刚回来时会做出不同决策。
2. 连续未回复后进入克制跟随，不继续刷屏。
3. 有未完成话题时优先延续，不随机开新话题。

### 4.5 Proactive Generator

目标：

- `src/core/initiative/generator.py`
- `YunxiPromptBuilder.build_proactive_prompt()`

生成上下文必须包含：

1. Persona profile。
2. Relationship profile。
3. HeartLake 当前情绪。
4. Perception 当前电脑环境。
5. Continuity 最近对话和 open_threads。
6. Initiative event 候选。
7. Expression context 表达姿态。

验收：

1. 主动消息必须由真实 LLM 生成。
2. 禁止恢复硬编码 fallback 文案。
3. 本地 Ollama 可用时，至少有一组真实 Ollama 主动消息测试。
4. 云端模型可用时，至少有一组云端真实 LLM 主动消息对照测试。
5. 生成结果要像“云汐自己想找远说话”，不能像系统通知或计划任务。

### 4.6 Expression Context

目标：

- `src/core/initiative/expression_context.py`

表达姿态示例：

1. `warm_professional`：远在工作或编程时，温和克制但不客服化。
2. `gentle_comfort`：远压力或低落时，安静陪伴。
3. `warm_reunion`：远离开后回来时，有重逢感。
4. `playful_close`：轻松亲近、可玩笑，但不过度甜腻。
5. `quiet_companion`：只短短陪一句，不打扰。
6. `restrained_followup`：之前主动未回复时，保持克制。

验收：

1. Expression context 只作为 LLM 引导，不直接决定固定句子。
2. 同一个事件在不同姿态下应生成不同语气。
3. 用户正在忙时，云汐应更短、更克制。

### 4.7 Continuity Persistence

目标：

- 增强 `src/core/initiative/continuity.py`
- 新增 `data/runtime/continuity_state.json`

必须补齐：

1. relationship_summary。
2. emotional_summary。
3. user_style_summary。
4. open_threads。
5. proactive_cues。
6. recent_topics。
7. unanswered_proactive_count。
8. recent_proactive_count。
9. user_returned_recently。
10. comfort_needed / task_focus / fragmented_chat。

验收：

1. 重启 daemon 后，最近关系状态和 open_threads 不丢失。
2. 主动未回复次数跨 tick 生效。
3. 最近话题能影响下一次主动消息。
4. 长对话后能形成压缩 summary，而不是只保留短窗口。

---

## 五、实现顺序

### P0-A：人格与关系 profile 迁入

1. 新建 persona / relationship 数据文件。
2. 实现 profile loader。
3. PromptBuilder 改为读取结构化 profile。
4. 增加真实 LLM 对话验收：确认身份、确认远的偏好、避免客服腔。

### P0-B：Continuity 持久化与 open_threads

1. 扩展 continuity state schema。
2. 增加 JSON 持久化。
3. Runtime 所有入口统一记录对话和主动消息。
4. 增加重启恢复测试。

### P0-C：生活事件库与三层事件系统

1. 清洗迁入 `life_events.json`。
2. 实现 event loader、time_rules、cooldown、active_events。
3. 事件只做 LLM 素材，不做直接输出。
4. 增加事件选择单元测试和真实 LLM 主动消息测试。

### P0-D：主动决策与生成上下文重建

1. 用多维 decider 替换当前偏简化规则。
2. 接入 expression context。
3. 主动 prompt 包含 persona、relationship、event、continuity、perception、emotion。
4. 增加 Ollama 与云端 LLM 两类真实生成测试。

### P0-E：日常模式真实验收

1. daemon 30 分钟稳定性测试。
2. 主动消息真实发送通道测试。
3. 用户忙碌、idle、刚回来、未回复、open thread 五类场景验收。
4. ConversationTester 增加人格/主动性质量断言。

### P1：实时兴趣与资源感知增强

1. 接入 realtime search，但网络不可用时必须降级。
2. Presence 增加游戏/全屏/高 CPU 负载勿扰策略。
3. 事件库增加用户兴趣动态扩展。

---

## 六、真实测试要求

迁移完成不能只跑函数级测试。必须包含以下真实 LLM 验收：

1. 本地 Ollama 对话测试：读取本机可用模型，完成被动对话和主动消息各一次。
2. 云端模型对照测试：使用 Moonshot/MiniMax/OpenAI 任一可用 provider 验证同类场景。
3. 人格一致性测试：云汐要能说清自己是住在电脑里的云汐，而不是助手。
4. 关系记忆测试：云汐要能记得远的基本档案和表达偏好。
5. 主动话题测试：主动内容必须引用事件、当前状态或 open thread 中至少一类上下文。
6. 克制测试：连续未回复后，主动消息明显减少或转为 restrained follow-up。
7. 反工具化测试：当用户没有要求执行任务时，云汐不能主动把话题扭成工具调用或任务计划。

---

## 七、完成定义

只有同时满足以下条件，才能把本迁移项从“重要待实现”改为“已完成”：

1. 新增 persona / relationship / initiative 数据文件和 loader。
2. PromptBuilder 不再只依赖硬编码身份文本。
3. Continuity 支持持久化和 open_threads。
4. 三层事件系统接入主动生成链路。
5. 主动判断从单纯规则阈值升级为多维 decider。
6. 主动消息真实 LLM 生成，并通过 Ollama 与至少一种云端模型的验收。
7. DEV_LOG 中记录测试命令、模型名称、通过结果和未覆盖风险。
