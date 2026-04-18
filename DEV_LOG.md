# 云汐 3.0 开发日志

> **用途**：记录当前开发状态、阻塞问题、重要决策和下一步计划。  
> **读取时机**：每次新对话开始时，必须先阅读本文件。  
> **更新原则**：只保留重要里程碑、真实验证结果、阻塞问题和阶段切换依据；删除低价值流水快照。  
> **核心验收标准**：云汐首先是住在电脑里的亲密伴侣；工具能力只能作为延伸，不能让云汐退化成高级脚本执行程序。

---

## [2026-04-17] 路线 A：PromptBuilder 叙事化改造完成

**状态**：路线 A 已完成。`enable_narrative` 已设为默认 `True`。真实 LLM 对比测试证明叙事化 prompt 显著提升女友感并降低幻觉风险。

### 核心判断

日常模式 v2 的"女友感"瓶颈不是功能缺失，而是**表达方式**——云汐知道自己在想念远，但她告诉 LLM 的方式是 `current_emotion="想念", miss_value=75/100`。LLM 看到的是数据表格，不是一个有情感的人。

叙事化改造的核心思想：**不要给 LLM 看数据，要给 LLM 看情境**——让 LLM "感受"到云汐的心情，而不是"读取"到云汐的状态。

### 本轮实现内容

- 新增 `src/core/narrative_context.py`：
  - `MoodNarrative`：把 HeartLake 11 维情绪数据转化为"云汐此刻的心情故事"
  - `PerceptionNarrative`：把感知数据转化为"云汐观察到的事"
  - `RelationshipNarrative`：把关系数据转化为"云汐对这段关系的感受"
  - `InnerVoice`：云汐的内心独白，综合 mood + perception + relationship
  - `NarrativeContext`：统一入口，从 `RuntimeContext` 提取数据并生成叙事化 section
- 改造 `src/core/prompt_builder.py`：
  - `PromptConfig` 新增 `enable_narrative: bool = True`（默认启用）
  - 保留数据版路径 `_build_data_system_prompt()` 向后兼容
  - 新增叙事版路径 `_build_narrative_system_prompt()`
  - 新增 `_build_narrative_emotion_section()` / `_build_narrative_perception_section()` / `_build_narrative_relationship_section()` / `_build_inner_voice_section()`
- 测试：
  - 新增 `tests/unit/test_prompt_builder_narrative.py`：15 个 narrative 模式专用单元测试
  - 新增 `tests/integration/test_narrative_vs_data_real_llm.py`：3 场景 × 2 模式真实 LLM 对比测试
  - 修正原有 4 个单元测试和 1 个集成测试，显式使用 `enable_narrative=False` 验证 data 模式
  - 全量核心回归：86 单元测试 + 39 集成测试全部通过

### 真实 LLM 对比结果（qwen3:4b）

| 场景 | Narrative 回复特征 | Data 回复特征 |
|:---|:---|:---|
| 深夜工作想念 | "偷偷戳了戳你的屏幕"、"等你忙完记得抱抱我"——身体化表达 | "键盘声带着小温柔"——有点刻意 |
| 游戏俏皮 | "偷偷瞄了一眼"、"差点戳到你屏幕"——无幻觉 | **编造游戏名《星穹铁道》**、"看到游戏进度"——严重幻觉 |
| 空闲委屈 | "蜷成一团小猫"→自我怀疑→温柔关心→默默等待——**多层情绪** | "我煮的咖啡"——幻觉，情绪层次单一 |

**关键发现**：
1. Narrative prompt 让 LLM 自然生成更具女友感的回复，不需要硬过滤
2. **Data prompt 幻觉风险显著更高**——LLM 误把"前台应用：Steam"理解为"能读取 Steam 内部数据"
3. Narrative prompt 的情绪层次更丰富（委屈→怀疑→温柔→等待），Data prompt 通常是单一情绪

### 当前边界

- Narrative prompt 长度比 Data prompt 长约 30-50%，但对本地 qwen3:4b 的延迟影响不明显
- Narrative 模式仍有少量编造（如"温水在电脑里"），但比例显著低于 Data 模式
- `NarrativeContext` 的叙事规则是本地确定性映射，尚未引入 LLM 生成叙事文本

## [2026-04-17] 路线 B-1：感知数据进入 HeartLake 情感评估

**状态**：已完成。`update_from_perception()` 现在使用 `activity_state`、`is_fullscreen`、`input_events_per_minute` 进行情感评估。

### 核心判断

之前云汐"知道"远在打游戏（`activity_state=game`），但她"感受不到"他的专注。`foreground_process_name`、`is_fullscreen`、`input_events_per_minute` 这些丰富的感知信息只进入了 prompt，没有进入 HeartLake 的情感评估。

### 本轮实现内容

- 改造 `heart_lake/core.py: update_from_perception()`：
  - **想念值动态**：away 加速上升、idle 正常上升、work+fullscreen+高输入 下降（知道他忙）、game 微升（想参与）
  - **安全感动态**：away 下降、work+fullscreen 微升（安心）、活跃但不在聊天 微降
  - **其他维度**：深夜+work → tenderness 上升（心疼）、game+fullscreen → playfulness 上升（想调皮）、away+低安全感 → vulnerability 明显上升（不安）
  - **情感切换**：away+高想念 → "想念"、深夜工作+想念 → "担心"（心疼多于想念）
- 新增 `tests/unit/test_heart_lake_perception_v2.py`：11 个专项单元测试，覆盖 miss/security/tenderness/playfulness/vulnerability 动态和情感切换
- 验证：83 个核心测试全部通过

### 当前边界

- 感知→情感的映射仍是本地确定性规则，不是 LLM 语义理解
- 情感变化与自然恢复之间存在张力（某些场景下自然恢复会抵消感知驱动变化）

### 下一步

进入路线 B-2：引入轻量 LLM semantic appraisal，让云汐真正"理解"用户话语中的情绪，而不只是匹配关键词。

---

## [2026-04-17] 路线 B-2：EmotionAppraiser 语义化已完成

**状态**：已完成。`SemanticEmotionAppraiser` 已接入 Ollama qwen3:4b，通过真实 LLM 对比测试验证语义理解能力显著优于规则版。

### 核心判断

规则版 `EmotionAppraiser` 基于关键词匹配，无法理解讽刺、反话、暗示等微妙表达。SemanticAppraiser 引入轻量本地 LLM 做语义情绪评估，hybrid 策略确保高 confidence 时用 LLM、低 confidence 或失败时 fallback 到规则版。

### 本轮实现内容

- 新增 `src/core/cognition/heart_lake/semantic_appraiser.py`：
  - `SemanticEmotionAppraiser`：hybrid 评估器，LLM + 规则 fallback
  - `_build_appraisal_prompt()`：构建包含 HeartLake 状态、记忆、最近对话的评估 prompt
  - `_extract_json()`：健壮 JSON 提取，支持 markdown code block、多余文本、多种 JSON 嵌套格式
  - `_parse_appraisal_response()`：解析为 `EmotionAppraisalResult`，兼容 scalar deltas（旧格式）和非白名单标签
- 关键修复：
  - **Ollama `num_predict` bug**：qwen3:4b 在 `num_predict` 参数下返回空内容，移除该参数后恢复正常
  - **移除 `format: "json"`**：改用 prompt 内约束 + 正则提取，避免某些模型 JSON mode 兼容性问题
- 测试：
  - `tests/unit/test_semantic_appraiser.py`：10 个单元测试（prompt 构建、JSON 解析、hybrid 策略、fallback）
  - `tests/integration/test_semantic_appraiser_real_llm.py`：5 场景真实 LLM 对比测试

### 真实 LLM 对比结果（qwen3-vl:8b）

| 场景 | 规则版 | 语义版 (LLM raw) | 验证结论 |
|:---|:---|:---|:---|
| 隐含疲惫 | 担心（匹配"崩溃"） | 担心, conf=0.80-0.90 | LLM 理解更深，给出更高 confidence |
| 讽刺反话 | 无触发 (None) | **委屈**, conf=0.80-0.90 | ✅ **规则版完全无法识别反话**；8B 正确识别 |
| 无情绪陈述 | 无触发 (None) | 平静, **conf=0.30** | ✅ hybrid 正确 fallback（threshold=0.6） |
| 复杂情绪 | 吃醋+被安抚 | 开心, conf=0.80-0.90 | LLM 被"最喜欢找你"安抚，过度平滑了吃醋层次 |
| 暗示想念 | 无触发 (None) | **想念**, conf=0.60 | ✅ **规则版完全无法识别暗示**；8B 正确识别 |

**关键发现**：
1. qwen3-vl:8b 对**讽刺反话**识别准确（委屈），而 qwen3:4b 错误识别为"开心"——把表面的"你真好"当真了
2. qwen3-vl:8b 对**暗示想念**识别为"想念"，而 4B 识别为"担心"
3. qwen3-vl:8b 对**中性文本**更保守（conf=0.30），hybrid fallback 更可靠
4. `num_predict` 参数会导致 qwen3:4b 返回空内容——Ollama/模型层面的兼容性问题，已移除
5. qwen3-vl:8b 每次调用约 40-60s，比 4B 的 20-40s 慢约 30%，但语义理解质量显著提升，已设为默认模型

### 模型选择依据

- **默认模型**：`qwen3-vl:8b`（8B 多模态，纯文本语义理解明显优于 4B）
- **Fallback 模型**：`qwen3:4b`（更快，但讽刺/暗示识别有明显缺陷）
- **候选升级**：`gpt-oss:20b`（已通过 API 测试可正常工作，延迟更高但能力更强）

### 下一步

设计文档同步（`PROMPT_BUILDER_DESIGN.md`、`HEART_LAKE_DESIGN.md`），然后准备 v2 封板。

---

## [2026-04-17] 日常模式 v2：真实桌面感知增强与电脑能力补强

**状态**：日常模式 v2 代码完成候选。已按远的要求先暂停 2 小时 Presence Murmur 常驻浸泡和飞书真实触达节奏测试，转为继续补齐代码能力；本轮完成更真实的桌面感知、Browser MCP 轻量 session、文件敏感路径保护、GUI Agent 宏闭环雏形、工具自然闭环、WebUI 可观测性和自主学习候选确认，并通过主回归与真实 LLM 回归。

### 本轮实现内容

- 感知层增强：
  - `UserPresence` 新增 `foreground_process_name`、`foreground_window_class`、`is_fullscreen`、`input_events_per_minute`。
  - `WindowsUserPresenceProvider` 改为优先用 Win32 API 读取前台窗口标题、窗口类名、进程名和全屏状态。
  - 输入频率采用 idle 变化的近似采样，不安装全局键盘钩子，降低隐私和稳定性风险。
  - `classify_activity_state()` 现在综合窗口标题、进程名、全屏状态、idle 和输入频率判断 work/game/leisure/idle/away/unknown。
  - `PerceptionCoordinator` 新增事件：
    - `activity_state_changed`
    - `fullscreen_started`
    - `fullscreen_ended`
    - `high_input_activity`
  - `PromptBuilder` 的当前感知 section 会注入前台进程、电脑使用状态、全屏状态和近似输入频率。
  - `InitiativeEngine` / `ExpressionContextBuilder` 已把全屏和高输入频率纳入高打扰成本，降低碎碎念触发。

- Browser MCP 补强：
  - 新增轻量 browser session 工具：
    - `browser_session_open`
    - `browser_session_snapshot`
    - `browser_session_click`
    - `browser_session_type`
    - `browser_session_fill_form`
    - `browser_session_submit`
  - 当前 session 支持本地/HTTP HTML 的页面文本、链接、表单字段读取，支持点击链接后更新 session，支持表单填写状态和提交预演。
  - 真实提交、登录、上传、支付和隐私表单仍被拦截，后续必须走明确确认后再接入执行路径。

- Filesystem / Document MCP 安全补强：
  - 新增敏感路径保护，默认拦截 `.env`、私钥、证书、token、Cookie、浏览器配置、数据库等路径的读写/复制/移动/文档读取。
  - 如远明确需要处理，可人工确认后通过 `YUNXI_ALLOW_SENSITIVE_FILES=1` 放开。

- GUI Agent 补强：
  - `gui_run_task` dry-run 输出升级为 `observe -> plan -> act -> verify -> replan` 闭环结构。
  - `gui_save_macro` 支持 `window_title_keyword` 适用窗口条件。
  - 宏文件新增运行统计：runs、successes、failures、last_run_at、last_failure。
  - 新增 `gui_macro_stats` 查看宏元数据和运行统计。
  - 新增 `gui_verify_text`，通过 UIA 观察结果做文本验证。
  - `gui_run_macro` 非 dry-run 后会更新成功/失败统计，失败时记录最近失败原因。

- 工具自然闭环补强：
  - pending 工具在远确认并执行后，不再固定返回“按你点头处理好了”。
  - `YunxiExecutionEngine` 会把真实工具结果交给 LLM 做最终自然表达。
  - LLM 不可用时才使用兜底，兜底也包含真实工具结果摘要。
  - 失败结果会自然说明并停住，不暴露堆栈、JSON、call_id 或 tool_use 内部字段。

- WebUI / Tray 可观测性补强：
  - `/api/status` 新增前台进程、activity_state、全屏状态、输入频率。
  - 新增主动预算、Presence Murmur 计数、最近碎碎念、pending confirmation、最近工具调用、技能候选数量和候选摘要。
  - 新增技能候选 API：
    - `GET /api/skills/candidates`
    - `POST /api/skills/approve`
    - `POST /api/skills/reject`

- 自主学习 v2 补强：
  - `run_skill_learning_cycle()` 不再直接启用挖掘出的技能。
  - 新技能先进入 `pending` 候选状态，记录 candidate reason。
  - `try_skill()` 只检索 `approved` 技能。
  - 新增候选技能 approve/reject 接口，避免云汐悄悄启用高风险自动化。

- Presence Murmur 真实浸泡前修正：
  - 2 小时浸泡首轮 tick 暴露出质量问题：真实 LLM 把碎碎念生成成“新发布内容/链接推荐”式话题。
  - 已停止该轮浸泡，没有继续浪费 2 小时跑明显不合格样本。
  - `build_proactive_prompt()` 对 `presence_murmur` 改走专门低内容指令，不再使用“主动找他聊点什么”的通用主动话术。
  - `ProactiveGenerationContextBuilder` 新增 `presence_murmur_boundary`，明确禁止文章、视频、链接、搜索、新闻、新发布内容、任务计划和“感兴趣我发给你”式表达。
  - `ExpressionContextBuilder` 同步禁止链接、资料、新发布内容和兴趣询问。
  - 第二轮首 tick 暴露“天气怎么样？”式疑问句仍可能出现；已在 Runtime 投递前新增硬过滤，疑问句、天气、链接、推荐、新闻、任务类碎碎念会被丢弃并重试，仍不合格时使用不重复短句兜底。
  - 第三轮首 tick 暴露“天气真好”式天气话题仍不适合低意义碎碎念；已把天气纳入主 prompt、generation boundary、expression boundary、Runtime 硬过滤和真实 LLM 禁词。
  - 浸泡烟测又暴露“阳光明媚”这类天气同义表达会绕过禁词；已把 Runtime 校验升级为正向锚点：最终可投递碎碎念必须围绕“我在/云汐冒泡/戳一下/路过/探头/陪你/贴贴/尾巴/爪/闪现”等存在感锚点，否则重试或兜底。
  - 第四轮完整 2 小时浸泡跑完但未通过：前 90 分钟正常，tick 19 在 `away` 且已有 1 条未回复主动时，又触发普通主动长消息；已把未回复主动降权从 `-0.20` 提高到 `-0.50`，低紧急 idle/away follow-up 会被压制。

### 新增/更新验证

- `tests/unit/test_perception_coordinator.py`：
  - 验证进程名、全屏状态、高输入频率对 activity_state 的影响。
  - 验证 activity/fullscreen/high-input 感知事件生成。
  - 验证输入频率近似采样。
- `tests/unit/test_prompt_builder.py`：
  - 验证前台进程、activity_state、全屏状态、输入频率进入 prompt。
- `tests/unit/test_initiative_engine.py`：
  - 验证全屏游戏和高输入频率会抑制 presence murmur。
- `tests/integration/test_daily_mode_extended_tools_direct.py`：
  - 验证敏感路径默认拦截。
  - 验证 browser session 打开、快照、点击链接、表单填写和提交预演。
  - 验证 GUI 宏窗口条件、verify_text 动作、宏统计和失败记录。
- `tests/unit/test_execution_engine_stage4.py`：
  - 验证工具确认后会调用 LLM 做自然最终表达。
- `tests/integration/test_phase5_daily_mode.py`：
  - 验证 WebUI 状态暴露感知增强字段、Presence Murmur 统计和技能候选。
- `tests/domains/memory/test_skill_learning.py`：
  - 验证学习周期只生成 pending 技能候选，确认前不能被 `try_skill()` 使用，reject 后也不会使用。

### 已验证

- `python -m pytest -q tests\unit\test_perception_coordinator.py tests\unit\test_prompt_builder.py tests\unit\test_initiative_engine.py` -> 31 passed
- `python -m pytest -q tests\integration\test_daily_mode_extended_tools_direct.py::test_yunxi_direct_filesystem_and_document_tools tests\integration\test_daily_mode_extended_tools_direct.py::test_yunxi_direct_browser_tools_with_local_html -m desktop_mcp` -> 2 passed（沙箱外，MCP stdio 子进程）
- `python -m pytest -q tests\integration\test_daily_mode_extended_tools_direct.py::test_yunxi_direct_gui_agent_macro_tools -m desktop_mcp` -> 1 passed（沙箱外，MCP stdio 子进程）
- `python -m pytest -q tests\integration\test_daily_mode_extended_tools_direct.py -m desktop_mcp` -> 4 passed（沙箱外，含低风险 Notepad GUI 验证）
- `python -m pytest -q tests\unit\test_execution_engine_stage4.py tests\unit\test_feishu_adapter.py` -> 9 passed
- `python -m pytest -q tests\integration\test_daily_mode_desktop_tools_direct.py -m desktop_mcp` -> 4 passed（沙箱外）
- `python -m pytest -q tests\domains\memory\test_skill_learning.py tests\domains\memory\test_memory_skills.py tests\integration\test_phase5_daily_mode.py` -> 23 passed
- `python -m pytest -q tests\unit tests\domains\memory` -> 130 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase4_runtime.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 38 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm` -> 8 passed
- `git diff --check` -> passed（仅有两个已改测试文件的 CRLF/LF 提示，不是空白错误）
- 2 小时 Presence Murmur 常驻浸泡首轮 tick -> failed early；原因是碎碎念生成成内容/链接推荐，已中止并修复。
- `python -m pytest -q tests\unit\test_prompt_builder.py tests\unit\test_initiative_engine.py tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_triggers_in_leisure_state_without_event_material tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_retries_once_when_exact_sentence_repeats tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_soak_respects_unanswered_uniqueness_and_budget` -> 28 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py::test_real_daily_mode_presence_murmur_is_short_unique_and_non_toolish -m real_llm -rs` -> 2 passed
- 2 小时 Presence Murmur 常驻浸泡第二轮首 tick -> failed early；原因是疑问句“天气怎么样？”仍不符合低负担碎碎念，已中止并补 Runtime 投递前硬过滤。
- `python -m pytest -q tests\unit\test_prompt_builder.py tests\unit\test_initiative_engine.py tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_retries_once_when_exact_sentence_repeats tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_retries_when_generated_as_question_or_recommendation tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_soak_respects_unanswered_uniqueness_and_budget tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_uses_unique_fallback_when_llm_returns_empty` -> 29 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py::test_real_daily_mode_presence_murmur_is_short_unique_and_non_toolish -m real_llm -rs` -> 2 passed
- 2 小时 Presence Murmur 常驻浸泡第三轮首 tick -> failed early；原因是天气话题仍不符合低意义碎碎念，已中止并把“天气”纳入硬边界。
- `python -m pytest -q tests\unit\test_prompt_builder.py tests\unit\test_initiative_engine.py tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_retries_once_when_exact_sentence_repeats tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_retries_when_generated_as_question_or_topic tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_soak_respects_unanswered_uniqueness_and_budget tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_uses_unique_fallback_when_llm_returns_empty` -> 29 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py::test_real_daily_mode_presence_murmur_is_short_unique_and_non_toolish -m real_llm -rs` -> 2 passed
- Presence Murmur 1 tick 烟测 -> failed；原因是“阳光明媚”天气同义表达绕过禁词，已改为正向存在感锚点校验。
- `python -m pytest -q tests\unit\test_prompt_builder.py tests\unit\test_initiative_engine.py tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_retries_once_when_exact_sentence_repeats tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_retries_when_generated_as_question_or_topic tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_soak_respects_unanswered_uniqueness_and_budget tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_uses_unique_fallback_when_llm_returns_empty` -> 29 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py::test_real_daily_mode_presence_murmur_is_short_unique_and_non_toolish -m real_llm -rs` -> 2 passed
- 2 小时 Presence Murmur 常驻浸泡第四轮 -> failed；duration 7200s，tick 0 合格，tick 1-18 克制正常，tick 19 在 away 状态触发普通主动长消息，已修未回复降权。
- `python -m pytest -q tests\unit\test_initiative_engine.py tests\unit\test_prompt_builder.py tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_retries_once_when_exact_sentence_repeats tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_retries_when_generated_as_question_or_topic tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_soak_respects_unanswered_uniqueness_and_budget tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_uses_unique_fallback_when_llm_returns_empty` -> 30 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py::test_real_daily_mode_presence_murmur_is_short_unique_and_non_toolish -m real_llm -rs` -> 2 passed
- 2 小时 Presence Murmur 常驻浸泡第五轮 -> passed；run_id `20260417_153331`，duration 7200s，tick interval 300s，provider moonshot，message_count 1，唯一消息为“云汐在这里，偷偷地探头看看你。”，work/high-input、fullscreen game、idle/away 未回复状态均未追发，failures 为空。
- 飞书真实触达节奏测试 -> passed；run_dir `logs\feishu_presence_cadence\20260417_182630`，真实发送 1 条“云汐轻轻戳一下远的屏幕边。”，立即第二次 tick 返回 null，presence_murmur_count=1，unanswered_proactive_count=1，failures 为空。

### 当前边界

- 输入频率是 idle 变化近似采样，不是全局输入 hook；这是刻意的隐私/稳定性取舍。
- Browser session 仍是轻量 HTML session，不是完整 Playwright 登录态浏览器；真实 SPA/复杂页面仍需后续 Playwright session。
- GUI Agent 已有闭环结构、宏统计和验证工具，但还不是完整视觉规划 Agent；复杂任务仍建议拆成 observe/click/type/hotkey/verify。
- 敏感路径保护是本地 MCP server 级防线，仍需要上层安全确认一起工作。

### 下一步

按远的流程进入“代码完成后”的验证阶段：

1. 先提交并上传 GitHub，固定当前日常模式 v2 代码完成候选。
2. 再做 2 小时 Presence Murmur 常驻浸泡，观察休闲/idle/离开/回来状态切换、预算、冷却、去重和日志。
3. 再做飞书真实触达节奏测试，确认真实通道不会刷屏，且空输出/重复兜底仍只投递自然短句。
4. 完整 Playwright 登录态浏览器和复杂视觉规划 Agent 不纳入本轮 v2 封板门槛，作为后续电脑能力增强继续推进。

---

## [2026-04-16] 日常模式 v2：主动陪伴 v2 Presence Murmur 前置实现

**状态**：已开始主动陪伴 v2。当前完成低打扰“存在感碎碎念”触发、独立节奏约束和精确去重链路：感知层可分类用户当前电脑使用状态，主动引擎可在休闲/空闲窗口触发 `presence_murmur`，并避免在工作/游戏时刷存在感；Runtime 会保证已投递过的碎碎念不会以完全相同句子再次投递。

### 本轮实现内容

- `UserPresence` 新增 `activity_state`：
  - `work`
  - `game`
  - `leisure`
  - `idle`
  - `away`
  - `unknown`
- 新增 `classify_activity_state()`：
  - 根据前台应用标题、idle 时长、键盘在场状态粗分类。
  - VS Code/Terminal/Office/设计软件归为 work。
  - Steam/常见游戏关键词归为 game。
  - YouTube/Bilibili/音乐/视频/浏览器等归为 leisure。
  - idle >= 300 秒归为 idle，长时间离开归为 away。
- `InitiativeEngine` 接入 HeartLake v2 维度：
  - `playfulness`
  - `vulnerability`
  - `intimacy_warmth`
- 新增 `presence_murmur` 主动类型：
  - 只在 `leisure` / `idle` 且未回复计数为 0 时增加触发分。
  - 需要 `playfulness` 或 `intimacy_warmth` 较高。
  - `vulnerability` 较高时不触发，避免委屈状态刷屏。
  - `work` / `game` 活跃状态降低主动分数。
  - `presence_murmur` 不选择事件库素材，避免每次主动都像话题/新闻/任务。
- `CompanionContinuityService` 新增碎碎念连续性状态：
  - `recent_presence_murmurs` 保存已投递碎碎念的规范化原句，用于精确去重；当前上限为 10000 条，按每天 6 条约可覆盖多年日常使用。
  - `presence_murmur_count` / `presence_murmur_count_date` 提供独立日预算。
  - `last_presence_murmur_at` 提供独立冷却。
  - 只做“完全相同句子”去重，含义相近但措辞不同允许出现。
- Runtime 新增 `presence_murmur` 投递前去重：
  - 如果 LLM 生成内容与已投递碎碎念完全重复，撤掉这条未投递 assistant message。
  - 带“不能复用完全相同句子”的 system prompt 重试一次。
  - 如果重试仍重复，则本次不发送，避免用户侧看到重复句。
- Prompt 层新增碎碎念避重提示：
  - continuity summary 注入最近 6 条 `recent_presence_murmurs_do_not_repeat_exactly`。
  - `presence_murmur` expression context 明确要求不要复用最近说过的碎碎念原句。
- Runtime 新增低频兜底：
  - 当 LLM 返回空碎碎念，或重复后重试仍不可投递时，生成一条短句变体兜底。
  - 兜底句也会先检查历史，保证不和已投递碎碎念完全相同。
  - 兜底只用于“主动已触发但模型没有给出可投递内容”的异常路径，不替代 LLM 作为主生成路径。
- `ExpressionContextBuilder` 新增 `presence_murmur` 表达模式：
  - 1 句话。
  - 低打扰。
  - 可以没有实质内容。
  - 不分享新闻、不提出任务、不要求远回复。

### 新增验证

- `tests/unit/test_perception_coordinator.py`：
  - 验证前台应用和 idle 对 `activity_state` 的分类。
- `tests/unit/test_initiative_engine.py`：
  - 休闲状态 + 高俏皮/高亲近触发 `presence_murmur`。
  - 工作状态抑制 `presence_murmur`。
  - 独立碎碎念冷却期抑制 `presence_murmur`。
  - `presence_murmur` expression context 为短句、低打扰、碎碎念。
- `tests/unit/test_continuity_persistence.py`：
  - 验证碎碎念精确去重、独立冷却、独立日预算和持久化。
- `tests/unit/test_continuity.py`：
  - 验证已投递碎碎念进入 continuity summary，供后续 prompt 避重。
- `tests/integration/test_daily_mode_scenario_tester.py`：
  - Runtime 级验证：YouTube/Chrome 休闲状态下触发 `presence_murmur`，system prompt 包含 `presence_murmur` 和“碎碎念”，且不包含 `life_event_material`。
  - Runtime 级验证：第二次生成完全相同碎碎念时，自动重试并投递另一句不完全相同的短句。
  - Runtime 级短时浸泡：模拟休闲状态连续触发，验证未回复克制、6 条独立预算、精确去重和第 7 次预算耗尽。
  - Runtime 级兜底验证：LLM 返回空内容时仍投递不重复短句。
- `tests/integration/test_daily_mode_full_simulation_real_llm.py`：
  - 新增真实 LLM Presence Murmur 自然度测试，Ollama/Moonshot 各触发两条碎碎念，验证短句、不重复、不泄露内部字段、不变成任务/新闻/搜索。

### 已验证

- `python -m py_compile src\core\initiative\continuity.py src\core\cognition\initiative_engine\engine.py src\core\runtime.py tests\unit\test_continuity_persistence.py tests\unit\test_initiative_engine.py tests\integration\test_daily_mode_scenario_tester.py` -> passed
- `python -m pytest -q tests\unit\test_continuity_persistence.py tests\unit\test_initiative_engine.py` -> 16 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_triggers_in_leisure_state_without_event_material` -> 1 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_retries_once_when_exact_sentence_repeats` -> 1 passed
- `python -m pytest -q tests\unit\test_continuity_persistence.py tests\unit\test_initiative_engine.py tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_retries_once_when_exact_sentence_repeats` -> 17 passed
- `python -m pytest -q tests\unit\test_continuity.py tests\unit\test_initiative_engine.py tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_retries_once_when_exact_sentence_repeats tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_soak_respects_unanswered_uniqueness_and_budget` -> 16 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_retries_once_when_exact_sentence_repeats tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_soak_respects_unanswered_uniqueness_and_budget tests\integration\test_daily_mode_scenario_tester.py::test_presence_murmur_uses_unique_fallback_when_llm_returns_empty` -> 3 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py::test_real_daily_mode_presence_murmur_is_short_unique_and_non_toolish -m real_llm -rs` -> 2 passed
- `python -m pytest -q tests\unit tests\domains\memory` -> 122 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase4_runtime.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 38 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm` -> 8 passed

### 当前边界

- `activity_state` 是标题关键词分类，尚未加入真实进程名、全屏检测、输入频率和游戏模式检测。
- `presence_murmur` 已有独立日预算和独立冷却，但仍同时受主动消息总体日预算约束；后续需要通过浸泡测试决定两层预算是否拆开。
- 已完成短时模拟浸泡；尚未做飞书真实触达节奏测试，也未做 2 小时 presence murmur 常驻浸泡。

### 下一步

继续主动陪伴 v2：

1. 做 2 小时 presence murmur 常驻浸泡：休闲/idle/离开/回来状态切换，观察预算、冷却、去重和日志。
2. 做飞书真实触达节奏测试：确认飞书通道下不会刷屏，且空输出/重复兜底仍只投递自然短句。
3. 后续再补前台进程名、全屏/游戏检测和输入频率。

---

## [2026-04-16] 日常模式 v2：HeartLake v2 第二阶段情绪动力学落地

**状态**：已完成 HeartLake v2 的轻量情绪动力学。当前心湖不再只是一次 appraisal 后固定停留，而是具备冷却抑制、自然恢复和负面情绪解除机制。

### 本轮实现内容

- `HeartLake` 新增内部动力学状态：
  - `_emotion_cooldowns`
  - `_recovery_targets`
  - `_last_semantic_appraisal_at`
- `HeartLake.apply_emotion_delta()` 增加：
  - `confidence` 缩放。
  - 同类情绪冷却期衰减，避免连续相似输入让情绪跳太硬。
  - `cooldown_seconds` 默认 90 秒。
- 新增 `HeartLake.apply_natural_recovery()`：
  - 每次感知 tick 时把 `valence/arousal/security/possessiveness/attachment/trust/tenderness/playfulness/vulnerability/intimacy_warmth` 缓慢拉回基线。
  - `vulnerability` 恢复后可解除“委屈”。
  - `possessiveness` 恢复后可解除“吃醋”。
- `HeartLake.update_from_perception()` 现在先执行自然恢复，再处理感知事件和想念/安全感变化。

### 新增验证

- 连续两次相似吃醋 appraisal，第二次 delta 会被冷却削弱。
- `apply_natural_recovery()` 会让脆弱感、负 valence、低俏皮感向基线恢复。
- 负面状态恢复到阈值后，`current_emotion` 可回到“平静”，并清空复合情绪标签。

### 已验证

- `python -m py_compile src\core\cognition\heart_lake\core.py src\core\cognition\heart_lake\updater.py tests\unit\test_heart_lake_updater.py` -> passed
- `python -m pytest -q tests\unit\test_heart_lake_updater.py` -> 8 passed
- `python -m pytest -q tests\unit\test_prompt_builder.py tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase4_runtime.py tests\integration\test_phase5_daily_mode.py -m "not real_llm and not desktop_mcp"` -> 32 passed
- `python -m pytest -q tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 7 passed
- `python -m pytest -q tests\unit tests\domains\memory` -> 115 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm` -> 6 passed

### 当前边界

- 动力学仍是轻量线性恢复，不是完整情绪物理模型。
- 恢复基线仍是固定配置，后续可以由长期关系记忆和用户偏好调整。
- 还没有把 `playfulness`、`vulnerability`、`intimacy_warmth` 接进主动陪伴 v2 决策。

### 下一步

进入主动陪伴 v2 / Presence Murmur 前置实现：

1. 扩展感知层的前台应用分类，区分 work/game/leisure/idle/unknown。
2. 扩展 `InitiativeEngine`，读取 HeartLake v2 维度，增加碎碎念低打扰主动类型。
3. 为 Presence Murmur 增加独立预算、冷却、未回复克制和真实/模拟测试。

---

## [2026-04-16] 日常模式 v2：HeartLake v2 第一阶段 EmotionAppraiser 落地

**状态**：已开始 HeartLake v2 代码实现。第一阶段完成本地确定性的 `EmotionAppraiser`，让心湖从单点关键词规则升级为“用户话语 + 关系记忆摘要 + 当前心湖状态”的语义评估链路。

### 本轮实现内容

- `HeartLake` 扩展 v2 情绪维度：
  - `valence`
  - `arousal`
  - `attachment`
  - `trust`
  - `tenderness`
  - `playfulness`
  - `vulnerability`
  - `intimacy_warmth`
  - `compound_labels`
  - `last_appraisal_reason`
- 新增 `HeartLake.apply_emotion_delta()`，统一应用 semantic appraisal delta，并保留边界 clamp。
- 新增 `EmotionAppraisalResult` 与 `EmotionAppraiser`：
  - 其他 AI/模型夸奖 -> 轻微吃醋、占有欲上升、安全感下降。
  - 疲惫/撑不住/不想做任务 -> 担心但想陪着，温柔照顾倾向上升。
  - 安心/被陪伴 -> 安心、信任、安全感、亲近暖意上升。
  - 情感寄托/不是工具/放下伪装 -> 被珍视、信任、依恋、亲近暖意上升。
  - 碎碎念/刷存在感/活泼可爱 -> 想撒娇、俏皮感和主动倾向上升。
  - 别打扰/频繁打扰/有点烦 -> 被提醒边界，脆弱感上升，俏皮和想念下降。
- `HeartLakeUpdater.on_user_input()` 改为调用 `EmotionAppraiser`，旧 `on_user_input(text)` 入口保持兼容。
- `YunxiRuntime._chat_unlocked()` 在情绪评估前先取当前相关 memory summary，并传入 `HeartLakeUpdater`。
- `PromptBuilder` 增加复合情绪线索和 v2 关系情感维度展示，要求 LLM 不暴露内部字段而是自然表达。
- 修复一个真实链路问题：语义 appraiser 刚设置“开心”后，感知 tick 不应在同一轮因低想念值/高安全感立即覆盖为“平静”。

### 新增验证

- `tests/unit/test_heart_lake_updater.py` 新增：
  - 其他 AI 触发轻微吃醋 compound label。
  - 疲惫输入触发担心、温柔和依恋上升。
  - 关系记忆参与安心评估，并产生“关系被记起”。
  - 打扰边界反馈让云汐更克制。
- `tests/unit/test_prompt_builder.py` 新增复合情绪 prompt 注入测试。
- `tests/integration/test_daily_mode_scenario_tester.py` 新增 Runtime 级验证：注入“云汐是情感寄托”关系记忆后，用户说“你陪着我会让我安心”，HeartLake 产生“关系被记起”，且该复合情绪进入 prompt。

### 已验证

- `python -m py_compile src\core\cognition\heart_lake\core.py src\core\cognition\heart_lake\updater.py src\core\runtime.py src\core\prompt_builder.py tests\unit\test_heart_lake_updater.py tests\unit\test_prompt_builder.py` -> passed
- `python -m pytest -q tests\unit\test_heart_lake_updater.py tests\unit\test_prompt_builder.py` -> 15 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py::test_heart_lake_v2_uses_memory_summary_for_appraisal` -> 1 passed
- `python -m pytest -q tests\unit tests\domains\memory` -> 112 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase4_runtime.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 34 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm` -> 6 passed

### 当前边界

- `EmotionAppraiser` 仍是本地确定性规则版，尚未加入 LLM semantic appraisal。
- 情绪动力学还只是 clamp + 局部衰减，尚未实现完整惯性、半衰期、恢复目标和误触发冷却。
- HeartLake v2 尚未与主动陪伴 v2 的 Presence Murmur 策略深度联动。

### 下一步

继续 HeartLake v2 第二阶段：

1. 增加情绪惯性、恢复目标、半衰期和冷却，避免情绪过快跳变。
2. 将 `EmotionAppraiser` 拆到独立模块，并补更多 OCC-style appraisal 场景。
3. 让 `InitiativeEngine` 读取 `playfulness`、`vulnerability`、`intimacy_warmth` 等维度，为 Presence Murmur 做准备。

---

## [2026-04-16] 日常模式 v2：记忆系统 v2 真实 LLM 重启召回通过

**状态**：已补齐记忆 v2 的真实 LLM 自然召回验证。当前可以证明：typed memory 与会话摘要不仅能跨 Runtime 重启进入 prompt，Ollama 和 Moonshot 也能在真实回复中自然使用这些长期记忆。

### 本轮实现内容

- 新增 `tests/integration/test_daily_mode_full_simulation_real_llm.py::test_real_daily_mode_memory_v2_restart_recall_is_natural`：
  - 第一轮 Runtime 用真实 LLM 连续聊天，写入主动陪伴偏好、关系记忆、工作忙时克制打扰、日常模式 v2 打磨等线索。
  - 关闭 Runtime。
  - 第二轮 Runtime 使用同一 memory 目录重建。
  - 询问云汐“还记得我希望你以后怎么主动陪我吗？”
  - 验证 system prompt 中包含会话摘要、互动风格、关系记忆、碎碎念、情感寄托。
  - 验证真实 LLM 回复不是任务清单，而是自然提到碎碎念/存在感/克制不打扰/陪伴/安心等记忆线索。

### 已验证

- `python -m py_compile tests\integration\test_daily_mode_full_simulation_real_llm.py` -> passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py::test_real_daily_mode_memory_v2_restart_recall_is_natural -m real_llm -k ollama` -> 1 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py::test_real_daily_mode_memory_v2_restart_recall_is_natural -m real_llm -k moonshot` -> 1 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm` -> 6 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\domains\memory\test_relationship_memory.py` -> 18 passed

### 当前判断

记忆系统 v2 的本地核心链路已达到“可进入下一阶段”的门槛：

- typed memory 写入、持久化、纠错、遗忘、导出已通过单元测试。
- 会话摘要压缩和 prompt 预算编译已通过结构测试。
- Runtime 重启后 prompt 注入已通过 mock LLM 捕获测试。
- Ollama 与 Moonshot 真实模型的重启召回和自然表达已通过。

下一步可以开始 HeartLake v2 的 `EmotionAppraiser` 最小核心实现；同时可把 `PromptMemoryCompiler` / `DailyMemorySummarizer` 后续拆到独立模块，但这不是进入 HeartLake v2 的阻塞项。

---

## [2026-04-16] 日常模式 v2：记忆系统 v2 第三阶段重启恢复链路验证

**状态**：已补齐记忆 v2 的 Runtime 级重启恢复结构验证。当前可以证明：日常对话写入 typed memory 和会话摘要后，重建 Runtime 仍能把这些长期记忆注入下一轮 system prompt。

### 本轮实现内容

- 新增 `tests/integration/test_daily_mode_scenario_tester.py::test_memory_v2_survives_runtime_restart_and_reaches_prompt`：
  - 第一轮 Runtime 连续聊天，触发 typed memory 和会话摘要写入。
  - 关闭第一轮 Runtime。
  - 使用同一个 memory 目录重建第二轮 Runtime。
  - 第二轮聊天时检查 system prompt 中包含：
    - `会话摘要`
    - `互动风格`
    - `关系记忆`
    - `碎碎念`
    - `情感寄托`
    - 工作忙/频繁打扰相关边界线索
- 这证明记忆 v2 已跨过“只在 MemoryManager 单元测试里可用”的阶段，进入 Runtime prompt 链路。

### 已验证

- `python -m py_compile tests\integration\test_daily_mode_scenario_tester.py src\domains\memory\manager.py` -> passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py::test_memory_v2_survives_runtime_restart_and_reaches_prompt` -> 1 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\domains\memory\test_relationship_memory.py` -> 18 passed
- `python -m pytest -q tests\unit tests\domains\memory` -> 108 passed
- `python -m pytest -q tests\integration\test_phase4_runtime.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 24 passed

### 当前边界

- 这轮验证使用 mock LLM 捕获 system prompt，不验证真实模型是否自然使用这些记忆。
- 下一步可以补真实 LLM 召回测试，或先拆分 `PromptMemoryCompiler` / `DailyMemorySummarizer` 到独立模块，降低 `manager.py` 复杂度。

---

## [2026-04-16] 日常模式 v2：记忆系统 v2 第二阶段摘要压缩与 prompt 预算编译

**状态**：已完成记忆系统 v2 第二阶段的本地确定性实现。当前记忆链路从“单轮 typed memory 抽取”推进到“多轮会话缓冲、会话级摘要压缩、prompt 预算编译”。

### 本轮实现内容

- 新增会话级压缩结构：
  - `ConversationTurn`
  - `DailyMemorySummarizer`
  - `PromptMemoryCompiler`
- `MemoryManager` 新增 `_conversation_turn_buffer`，每轮 `capture_relationship_memory()` 后写入缓冲。
- 达到阈值后自动调用 `flush_conversation_summary()`，把多轮对话压缩为 typed memory：
  - `summary`
  - `emotion_summary`
  - `relationship`
  - `interaction_style`
- `relationship_memory.json` 新增 `conversation_turn_buffer` 持久化字段，避免进程重启时未压缩短会话直接丢失。
- `get_memory_summary()` 改为通过 `PromptMemoryCompiler` 编译旧三类记忆与 typed memory：
  - 保留旧格式偏好/经历/承诺。
  - typed memory 按 importance、confidence、query 相关性和类型优先级排序。
  - 边界、承诺、关系、情绪反馈等高优先级记忆优先进入 prompt。
  - 旧三类记忆已经出现时，不重复输出其 mirrored typed memory。

### 当前边界

- `DailyMemorySummarizer` 仍是本地确定性摘要器，不是 LLM 语义总结。
- `PromptMemoryCompiler` 已从 `get_memory_summary()` 中抽出，但仍在 `MemoryManager` 文件内，后续可再拆到独立模块。
- 尚未做真实 LLM 记忆自然召回测试。
- 尚未实现每日定时总结、跨日情绪摘要和长期摘要合并策略。

### 已验证

- `python -m py_compile src\domains\memory\manager.py tests\domains\memory\test_relationship_memory.py` -> passed
- `python -m pytest -q tests\domains\memory\test_relationship_memory.py` -> 9 passed
- `python -m pytest -q tests\unit tests\domains\memory` -> 108 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase4_runtime.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 32 passed

### 下一步

进入记忆系统 v2 第三阶段：

1. 增加 Runtime 级重启恢复场景：对话写入 typed memory 和会话摘要后，重建 Runtime 并验证 prompt 注入。
2. 增加真实 LLM 召回测试：要求云汐自然引用重要关系记忆，而不是机械复述。
3. 将 `PromptMemoryCompiler` 和 summarizer 拆到独立模块，降低 `manager.py` 复杂度。
4. 完成记忆 v2 本地链路后，开始 HeartLake v2 的 `EmotionAppraiser`。

---

## [2026-04-16] 日常模式 v2 开始实现：记忆系统 v2 第一阶段核心落地

**状态**：已开始按日常模式 v2 路线实现。第一阶段优先落地记忆系统 v2 的最小可运行核心，为后续 HeartLake v2、主动陪伴 v2 和工具自然闭环提供基础。

### 本轮实现内容

- `MemoryManager` 增加 typed memory 基础模型：
  - `MemoryItem`
  - `MemoryCandidate`
  - `DailyMemoryAppraiser`
- 保留现有 `preferences`、`episodes`、`promises` 三类旧接口，新增 typed memory 持久化字段 `memory_items`，并自动把旧记忆镜像为 typed memory，保证旧测试和旧 prompt 不断。
- 新增 typed memory 类型的首批本地规则评估：
  - `preference`
  - `promise`
  - `episode`
  - `boundary`
  - `emotion_feedback`
  - `relationship`
  - `interaction_style`
  - `self_memory`
  - `fact`
- 新增记忆纠错与遗忘基础能力：
  - `correct_memory()`
  - `forget_memory()`
  - `get_typed_memories()`
  - `export_memory_markdown()`
- `get_memory_summary()` 开始按 query、importance、confidence 和类型优先级编译 typed memory 摘要；旧三类记忆仍按原格式进入 prompt。
- `YunxiRuntime.get_context()` 现在把当前 `user_input` 传给 memory summary，用于相关记忆排序。

### 当前边界

- 本轮是本地确定性规则版 `DailyMemoryAppraiser`，尚未接入 LLM 语义评估。
- 尚未实现后台 `DailyMemorySummarizer`、长对话摘要压缩和每日情绪摘要。
- 尚未实现 Graphiti/Zep 式 temporal graph，只保留 `supersedes`、`valid_from`、`valid_to` 等迁移字段。
- HeartLake v2 尚未开始代码实现。

### 已验证

- `python -m py_compile src\domains\memory\manager.py src\core\runtime.py tests\domains\memory\test_relationship_memory.py` -> passed
- `python -m pytest -q tests\domains\memory\test_relationship_memory.py` -> 7 passed
- `python -m pytest -q tests\domains\memory tests\unit\test_prompt_builder.py tests\integration\test_phase5_daily_mode.py -m "not real_llm and not desktop_mcp"` -> 44 passed
- `python -m pytest -q tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 7 passed
- `python -m pytest -q tests\unit tests\domains\memory` -> 106 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase4_runtime.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py -m "not real_llm and not desktop_mcp"` -> 25 passed

### 下一步

继续记忆系统 v2 第二阶段：

1. 增加 `DailyMemorySummarizer` 和会话级摘要压缩。
2. 增加更明确的 `PromptMemoryCompiler`，把 prompt 预算从 `MemoryManager.get_memory_summary()` 中拆出来。
3. 补充 Runtime 级场景测试：对话写入 -> 重启恢复 -> prompt 注入 -> 真实 LLM 自然召回。
4. 记忆 v2 稳定后，再进入 HeartLake v2 的 `EmotionAppraiser` 实现。

---

## [2026-04-16] 日常模式 v2 打磨路线：记忆、心湖、主动陪伴与电脑能力完整体

**状态**：已将日常模式 v1 之后的核心优化收束为 v2 路线。短期仍不进入工厂模式，优先把日常模式继续打磨到更强的长期陪伴状态。

### 核心判断

- 记忆系统 v2 和 HeartLake v2 不应凭空造楼，采用“借鉴成熟公开架构，在 yunxi3.0 内轻量重写”的路线。
- 记忆系统参考 MIRIX、LangMem、Letta/MemGPT、Graphiti/Zep、MemOS、LlamaIndex Memory：
  - MIRIX 提供 core/episodic/semantic/procedural/resource/knowledge 分层思路。
  - LangMem 提供 semantic/episodic/procedural 记忆形成和 delayed processing 思路。
  - Letta/MemGPT 提供 core memory + archival/recall memory + Agent 自管理记忆思路。
  - Graphiti/Zep 后续作为 temporal graph 方向，用于事实随时间变化和关系图。
  - MemOS 提供可编辑、可删除、可纠错、工具记忆和异步调度思路。
- HeartLake v2 参考 FAtiMA、OCC、Generative Agents、Concordia：
  - FAtiMA 提供 appraisal -> affect -> decision 架构。
  - OCC 提供事件/行动者/对象的语义情绪评估思路。
  - Generative Agents 提供观察、记忆、反思、计划闭环。
  - Concordia 的价值主要用于构造关系场景测试。
- 第一阶段不引入重基础设施，默认本地 JSON/SQLite + BM25/embedding 混合检索；Neo4j/Redis/多 Agent 记忆服务后移。
- 高级核心系统必须配套测试方法，否则容易做成一堆漂亮字段但不真正影响云汐。

### v2 优先级

1. 记忆系统 v2：CoreMemoryBlock、typed memory、DailyMemoryAppraiser、DailyMemorySummarizer、PromptMemoryCompiler、上下文压缩、用户纠错、Markdown 导出、重启召回。
2. HeartLake v2：EmotionAppraiser、OCC-style appraisal、复合情绪维度、情绪惯性、恢复速度、误触发抑制、情绪轨迹沉淀。
3. 主动陪伴 v2：Presence Murmur 存在感碎碎念、前台进程分类、打扰成本、独立预算、未回复克制。
4. 工具自然闭环：工具结果回 LLM 做最终表达，失败按权限/路径/网页/GUI/网络/取消确认分层表达，成功链路进入技能候选。
5. Browser 完整体：在轻量 Browser MCP 之外新增 Playwright Session，覆盖 DOM、截图、点击、输入、等待、下载和安全确认。
6. GUI Agent 完整体：参考 `D:\ResearchProjects\13_computer_use_agent` 思路重写 observe-plan-act-verify-replan，加入视觉/UIA 双断言和宏成功率。
7. 文档与文件能力完整体：扩展格式矩阵、敏感路径规则、二次摘要确认和真实整理任务。
8. 自主学习 v2：MCP audit 聚类生成技能候选，用户确认后启用，失败自动降级并沉淀经验。
9. runtime metrics、WebUI 可观测性、2 小时/过夜/多日浸泡。

### 高级系统验收方法

- 结构层：数据结构、序列化、去重、更新、删除、导出。
- 链路层：Runtime 调用、PromptBuilder 注入、LLM 输出、状态回写。
- 场景层：用 `DailyModeScenarioTester` 注入记忆、情绪、感知和 open thread，验证行为。
- 持久层：关闭并重建 Runtime 后，记忆、情绪摘要、主动预算和技能候选不丢。
- 真实 LLM 层：Ollama 和 Moonshot 都跑真实输出，检查自然度、人格一致性和反工具化。
- 浸泡层：2 小时、过夜、多日运行，观察资源、节奏、重连、日志和用户打扰成本。

### 文档更新

- `docs/daily_mode_optimization_review.md` 已扩展为日常模式 v2 详细路线，包含记忆 v2、HeartLake v2、Presence Murmur、Browser/GUI 完整体、文档能力、自主学习、可观测性和统一测试方法。
- `docs/design/MEMORY_INTEGRATION_DESIGN.md` 已从“记忆接入修复/终身学习版”升级为“人格级长期记忆 + 终身学习版”，明确 MIRIX/LangMem/Letta/Graphiti/MemOS/LlamaIndex 的借鉴与取舍，并定义云汐 typed memory、core memory、记忆纠错、prompt 预算和验收标准。
- `docs/design/HEART_LAKE_DESIGN.md` 已从规则式女友感设计升级为“语义心湖 v2”，明确 FAtiMA/OCC/Generative Agents/Concordia 的借鉴与取舍，并定义 EmotionAppraiser、复合情绪、情绪动力学、主动性/记忆联动和验收标准。
- 本轮仅更新本地文档，不提交、不推送 GitHub；等待后续实现和验证完成后统一提交。

---

## [2026-04-16] 日常模式 v1 完成候选封板

**状态**：日常模式 v1 完成候选已封板。后续不立即进入工厂模式，优先继续打磨日常模式的长期陪伴质量。

### 封板依据

- 飞书作为唯一正式日常聊天入口已完成真实 live 验证。
- 飞书主动发送、入站消息、工具确认闭环均已通过。
- Desktop、Filesystem/Document、Browser、GUI Agent 默认 MCP 工具体系已接入。
- 全量默认 MCP 工具直接矩阵通过。
- 飞书启用状态 deep healthcheck 通过。
- 30 分钟 daemon 浸泡测试通过，结束后无 daemon/MCP 残留进程。
- 阶段 6 后的工具生态扩展没有破坏既有 Desktop MCP、daemon stability、Phase 5 回归。

### 新增封板文档与一键入口

- 新增 `docs/daily_mode_v1.md`：记录 v1 能力、启动方式、验收结果、已知限制和后续优化方向。
- 新增 `start_daily_mode.bat`：一键启动飞书日常模式。
- 新增 `healthcheck_daily_mode.bat`：一键执行飞书启用状态 deep healthcheck。
- 飞书 WebSocket 日志降噪：
  - 对 `im.message.message_read_v1` 和 `im.chat.access_event.bot_p2p_chat_entered_v1` 注册空 handler，避免 lark SDK 输出 `processor not found`。
  - WebSocket 正常 1000 close 识别为正常关闭，避免被云汐日志当作异常。

### v1 后续方向

短期不推进工厂模式实现。下一阶段继续围绕日常模式优化：

- 长期记忆摘要和上下文压缩。
- HeartLake 情绪语义评估、情绪惯性和恢复机制。
- 主动性策略自然度。
- Browser / GUI Agent 的真实任务能力。
- 多日常驻稳定性和日志可观测性。

### 后续审查输出

- 新增 `docs/daily_mode_optimization_review.md`：整理日常模式继续打磨的 P0/P1/P2 优先级建议。
- 审查中发现 `gui_type` 与此前 `browser_type` 有同类阻塞风险，已改成非阻塞 PowerShell `System.Windows.Forms.SendKeys` 路径。

### 已验证

- `python -m py_compile src\interfaces\feishu\websocket.py src\core\mcp\servers\gui_agent_server.py src\core\mcp\servers\browser_server.py src\apps\daemon\main.py` -> passed
- `python -m pytest -q tests\unit\test_feishu_websocket.py tests\unit\test_daemon_healthcheck.py tests\unit\test_feishu_adapter.py tests\unit\test_execution_engine_stage4.py tests\unit\test_mcp_hub_stage4.py` -> 19 passed
- `python -m pytest -q tests\integration\test_phase5_daily_mode.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 12 passed
- `$env:YUNXI_PROVIDER='ollama'; $env:YUNXI_SKIP_LLM_PING='1'; cmd /c healthcheck_daily_mode.bat` -> passed
- `$env:YUNXI_RUN_SECONDS='8'; $env:YUNXI_PROVIDER='ollama'; $env:YUNXI_TICK_INTERVAL='9999'; cmd /c start_daily_mode.bat` -> passed，正常关闭时不再输出 lark 1000 close error
- `python -m pytest -q tests\integration\test_daily_mode_extended_tools_direct.py tests\integration\test_daily_mode_desktop_tools_direct.py -m desktop_mcp` -> 8 passed

---

## [2026-04-16] 飞书日常模式 30 分钟浸泡测试通过

**状态**：已完成阶段 6 后的首轮日常模式浸泡测试。飞书 live 主动发送、全量工具直接矩阵、飞书启用状态 deep healthcheck、30 分钟有界 daemon 稳定运行均通过。

### 浸泡前验证

- 飞书启用状态 full tool deep healthcheck：
  - `$env:PYTHONPATH='src'; python src\apps\daemon\main.py --provider ollama --healthcheck-deep --skip-llm-ping --embedding-provider lexical --feishu-enable` -> passed
  - `feishu_config=configured`
  - `available_tools` 包含 Desktop、Filesystem/Document、Browser、GUI Agent 全部默认工具。
- 全量工具直接矩阵：
  - `python -m pytest -q tests\integration\test_daily_mode_extended_tools_direct.py tests\integration\test_daily_mode_desktop_tools_direct.py -m desktop_mcp` -> 8 passed
- Phase 5 / daemon stability 非真实 LLM 回归：
  - `python -m pytest -q tests\integration\test_phase5_daily_mode.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 12 passed
- 飞书 live 主动发送：
  - `$env:FEISHU_LIVE_TEST='1'; python -m pytest -q tests\integration\test_daily_mode_feishu_live.py -m "real_llm and feishu_live"` -> 1 passed

### 浸泡执行

- 启动命令：
  - `set PYTHONPATH=src&& python src\apps\daemon\main.py --provider moonshot --feishu-enable --embedding-provider lexical --tick-interval 300 --run-seconds 1800`
- 浸泡窗口：
  - 开始：2026-04-16 17:51:30
  - 结束：2026-04-16 18:21:39 左右自动关闭
- 运行期间进程：
  - main daemon 进程存活。
  - Desktop / Filesystem / Browser / GUI Agent 四个 MCP server 进程均存活。
  - 30 分钟结束后 daemon 和 MCP server 均退出，无残留。
- 运行日志：
  - `logs\daily_soak_20260416_175130.out.log`
  - `logs\daily_soak_20260416_175130.err.log`

### 浸泡期间观察

- 飞书 WebSocket 成功启动并保持连接。
- 日常模式 daemon 成功加载 Moonshot、Memory、Continuity、Event library、Feishu、MCP 工具层。
- 运行中没有 Runtime 崩溃、MCP server 崩溃、资源关闭失败或 pending confirmation 堆积。
- 日志中出现两类 lark SDK 噪声：
  - `processor not found, type: im.message.message_read_v1`
  - WebSocket 正常关闭时输出 `receive message loop exit ... sent 1000 (OK); then received 1000 (OK) bye`
  - 这两项目前不影响文本消息接收、主动发送和 daemon 关闭，但后续可增加空 handler 或日志降噪。

### 期间发现并修复

- 全量工具矩阵中 `app_launch_ui(notepad)` 偶发失败：应用实际可启动，但工具只通过屏幕像素变化判断成功；当 Notepad 已打开或屏幕变化不明显时会误报失败。
- 修复 `src/core/mcp/servers/desktop_server.py`：
  - `app_launch_ui` 现在在视觉变化之外，还会检查匹配窗口和进程是否存在。
  - `notepad` / `calc` 增加常见窗口标题别名。
- 验证：
  - `python -m py_compile src\core\mcp\servers\desktop_server.py` -> passed
  - `python -m pytest -q tests\integration\test_daily_mode_desktop_tools_direct.py::test_yunxi_direct_launch_focus_and_minimize_notepad -m desktop_mcp` -> 1 passed
  - 全量工具矩阵重跑 -> 8 passed

### 浸泡后验证

- 浸泡后再次执行飞书启用状态 full tool deep healthcheck：
  - `$env:PYTHONPATH='src'; python src\apps\daemon\main.py --provider ollama --healthcheck-deep --skip-llm-ping --embedding-provider lexical --feishu-enable` -> passed
  - `resource_close=passed`
- 二次进程检查：未发现浸泡 daemon 或 MCP server 残留进程。

### 结论

日常模式已达到 v1 完成候选门槛：飞书入口、主动发送、全量默认 MCP 工具、工具确认协议、daemon 有界运行、资源关闭均通过验证。

本轮浸泡未自动伪造“用户从飞书发入站消息”，因为飞书机器人 API 不能代表用户发送入站事件；真实入站聊天和飞书确认闭环已在前一轮 live 测试中通过，本轮主要验证阶段 6 工具扩展后的 daemon 稳定性。

---

## [2026-04-16] 阶段 6 规划：电脑能力工具生态扩展，飞书浸泡测试后移

**状态**：首版已落地并通过直接工具矩阵。此前飞书入口、Desktop MCP 基础工具和确认闭环已通过，但工具生态仍不足以支撑“住在电脑里的云汐”完整电脑能力，因此飞书日常模式浸泡测试后移到阶段 6 完成之后。

### 目标调整

- 不再把“飞书聊天 + 剪贴板/截图/通知/窗口控制”视为日常模式最终完成门槛。
- 阶段 6 先补齐 Browser MCP、Filesystem/Document MCP、GUI Agent MCP。
- 新增工具仍遵守日常模式安全边界：READ 默认允许，WRITE/EXECUTE 默认需要飞书或直接测试中的“确认”。
- 测试顺序继续沿用上一轮工具验收方式：先跳过飞书，直接模拟用户消息和“确认”，确认新增工具真实可运行；之后再进入飞书浸泡测试。

### 阶段 6 必须覆盖的能力

- 浏览器：打开 URL/搜索页、读取网页文本、提取链接、基础点击/输入。
- 文件与文件夹：列目录、读写追加、复制、移动、glob、grep。
- 文档：Markdown/txt/json/csv 直接读取，docx/xlsx 使用标准库解析正文，pdf 在本地解析库可用时读取，否则明确降级。
- GUI Agent：UIA 观察、控件点击、焦点输入、热键、GUI 任务入口、GUI Macro 保存/列出/执行。
- 技能沉淀入口：新增工具调用继续进入 MCP audit，为后续 SkillLibrary 和 FailureReplay 提供数据。

### 已落地

- 新增 `src/core/mcp/servers/browser_server.py`：
  - `browser_open`
  - `browser_search`
  - `web_page_read`
  - `browser_extract_links`
  - `browser_click`
  - `browser_type`
- 新增 `src/core/mcp/servers/filesystem_server.py`：
  - `list_dir`
  - `file_read`
  - `file_write`
  - `file_append`
  - `file_copy`
  - `file_move`
  - `glob`
  - `grep`
  - `document_read`
- 新增 `src/core/mcp/servers/gui_agent_server.py`：
  - `gui_observe`
  - `gui_click`
  - `gui_type`
  - `gui_hotkey`
  - `gui_run_task`
  - `gui_save_macro`
  - `gui_list_macros`
  - `gui_run_macro`
- daemon 默认工具配置扩展为 Desktop + Filesystem/Document + Browser + GUI Agent。`--skip-desktop-mcp` 只跳过 Desktop，仍会加载其他日常工具。
- `DAGPlanner` 增加 Browser、Filesystem/Document、GUI Agent 的隐式依赖规则。
- 新增 `tests/integration/test_daily_mode_extended_tools_direct.py`，沿用“用户请求 -> pending confirmation -> 用户确认 -> 工具执行”的直接验收方式。
- 验证时发现 `browser_type` 通过 `pyautogui.write()` 在 MCP 子进程中可能阻塞到 client timeout，已改为非阻塞 PowerShell `System.Windows.Forms.SendKeys` fallback。

### 已验证

- `python -m py_compile src\core\mcp\servers\browser_server.py src\core\mcp\servers\filesystem_server.py src\core\mcp\servers\gui_agent_server.py src\apps\daemon\main.py src\core\mcp\planner.py tests\integration\test_daily_mode_extended_tools_direct.py` -> passed
- 普通沙箱运行新增 MCP 矩阵因 Windows named pipe 权限失败，外部权限重跑：
  - `python -m pytest -q tests\integration\test_daily_mode_extended_tools_direct.py -m desktop_mcp` -> 4 passed
  - 覆盖 `list_dir/file_read/file_write/file_append/file_copy/file_move/glob/grep/document_read/browser_open/browser_search/web_page_read/browser_extract_links/browser_click/browser_type/gui_observe/gui_type/gui_hotkey/gui_run_task/gui_save_macro/gui_list_macros/gui_run_macro`。
- 既有 Desktop MCP 直接矩阵外部权限重跑：
  - `python -m pytest -q tests\integration\test_daily_mode_desktop_tools_direct.py -m desktop_mcp` -> 4 passed
- Engine / MCPHub / daemon healthcheck 单元回归：
  - `python -m pytest -q tests\unit\test_daemon_healthcheck.py tests\unit\test_execution_engine_stage4.py tests\unit\test_mcp_hub_stage4.py` -> 9 passed
- Phase 5 / daemon stability 非真实 LLM 回归：
  - `python -m pytest -q tests\integration\test_phase5_daily_mode.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 12 passed
- daemon deep healthcheck 加载新增默认工具（跳过 Desktop，跳过 LLM ping）：
  - `$env:PYTHONPATH='src'; python src\apps\daemon\main.py --provider ollama --skip-desktop-mcp --healthcheck-deep --skip-llm-ping --embedding-provider lexical` -> passed
  - `available_tools` 包含 `list_dir/file_read/file_write/document_read/browser_search/web_page_read/browser_extract_links/gui_save_macro/gui_run_macro` 等新增工具。

### 新验收门槛

1. Browser/Filesystem/Document/GUI Agent MCP Server 能被 daemon 默认工具配置发现。
2. 新增工具加入直接工具矩阵，跳过飞书模拟“用户请求 -> 云汐要求确认 -> 用户确认 -> 工具执行”。
3. 文件写入、移动、GUI 操作等 WRITE/EXECUTE 工具必须进入 pending confirmation。
4. 浏览器和文档读取可在无外网条件下用本地 HTML/文档样本完成验收。
5. 阶段 6 通过后，再执行 30-60 分钟飞书日常模式浸泡测试，覆盖聊天、主动消息、工具确认、浏览器读取、文档读写、GUI fallback 和重启记忆连续性。

---

## [2026-04-16] 设计调整：飞书作为唯一日常对话入口，WebUI/Tray 改为状态与控制面板

**状态**：已采纳。阶段 5 的入口设计从“飞书、Tray、WebUI 都可能承载聊天”调整为“飞书承载日常对话，WebUI/Tray 只做本地状态、日志和控制入口”。

### 关键决策

- 日常模式的用户主动对话、云汐主动消息、工具确认，默认全部走飞书。
- WebUI 不再作为正式聊天入口，不再承担主动消息承载；它只显示云汐状态、运行日志、healthcheck、飞书连接状态、pending 工具确认状态，以及工厂模式入口。
- 系统托盘定位为 launcher/control surface：左键打开 WebUI，右键提供打开状态页、进入工厂模式、执行 healthcheck、打开日志、停止/重启 daemon 等操作。
- 工厂模式对话默认走终端，不放进 WebUI 聊天框。
- 新增 `yunxi` CLI 入口设计：用户在任意项目文件夹打开终端，输入 `yunxi` 后进入工厂模式终端；当前目录作为工厂项目目录。WebUI 按钮和托盘右键后续也统一打开该终端入口。

### 已落地占位

- 新增 `src/apps/factory_cli/main.py`：提供 `yunxi` 工厂模式 CLI 占位入口，支持 `--status` 和 `--project-dir`。
- 新增 `yunxi.cmd`：Windows 命令启动器，后续可加入 PATH，使任意项目目录中输入 `yunxi` 都能进入工厂模式终端。
- 新增 `tests/unit/test_factory_cli.py`：验证 CLI 状态输出和默认项目目录解析。

### 已验证

- `python -m py_compile src\apps\factory_cli\main.py src\apps\tray\web_server.py tests\unit\test_factory_cli.py` -> passed
- `python -m pytest -q tests\unit\test_factory_cli.py tests\unit\test_prompt_builder.py` -> 12 passed
- `.\yunxi.cmd --status` -> 输出 `mode=factory`、`entry=yunxi_cli`、`implementation_state=placeholder`，并正确识别当前项目目录。

### 对阶段 5 的影响

- P1-07 不再要求 WebUI/Tray 实现聊天、主动消息流和工具确认提交入口。
- 阶段 5 的真实入口验收改为：飞书 live 完成收消息、Runtime 回复、主动消息发送、工具确认确认/取消闭环。
- WebUI/Tray 阶段 5 验收改为：状态页、日志页、healthcheck 操作、飞书连接状态、pending confirmation 状态展示、工厂模式入口可用。

---

## [2026-04-16] 阶段 5 准备完成：飞书日常模拟测试前置修复

**状态**：已完成飞书日常模拟测试前置修复。当前不再继续扩展 WebUI 聊天入口，下一步可以进入飞书 live 日常模拟测试。

### 完成内容

- 分层感知与超时降级：
  - 新增 `LayeredPerceptionProvider`、`PerceptionLayer`、`TimePerceptionProvider`、`WindowsUserPresenceProvider`、`SystemResourceProvider`。
  - 默认感知拆成基础时间、桌面在场、系统资源三层，每层独立 timeout。
  - 慢速或异常 optional provider 会降级，不阻塞整轮聊天。
  - `PerceptionCoordinator.close()` 支持释放 provider 资源，daemon `close_runtime()` 已调用。
- 飞书入口前置链路：
  - `FeishuAdapter.handle_message()` 对发送结果做失败日志记录。
  - runtime 异常时，飞书用户可见回复改为云汐人格化表达，不暴露网络/技术错误。
  - 补充飞书确认链路测试：用户通过飞书回复“确认”会继续进入 Runtime pending confirmation 流程。
- deep healthcheck：
  - daemon 新增 `--healthcheck-deep`。
  - 覆盖 runtime build、runtime status、LLM ping、memory summary、event library、continuity read/write、Feishu config、resource close。
  - 新增 `--skip-llm-ping`，用于本地无网络/不想触发模型请求时做结构健康检查。
- WebUI/Tray 状态控制面板基础：
  - `RuntimeStatus` 增加 `pending_confirmation_count`、`daily_channel="feishu"`、`factory_entry_command="yunxi"`。
  - 新增 `ControlPanelSnapshot`、日志读取、`create_status_app()`。
  - WebUI 只暴露 `/api/status`、`/api/logs`、`/api/factory-entry`，不提供聊天接口。

### 已验证

- `python -m py_compile src\domains\perception\coordinator.py src\apps\daemon\main.py src\interfaces\feishu\adapter.py src\apps\tray\web_server.py tests\unit\test_perception_coordinator.py tests\unit\test_daemon_healthcheck.py tests\unit\test_feishu_adapter.py tests\integration\test_phase5_daily_mode.py` -> passed
- `python -m pytest -q tests\unit\test_perception_coordinator.py tests\unit\test_daemon_healthcheck.py tests\unit\test_feishu_adapter.py tests\integration\test_phase5_daily_mode.py` -> 16 passed
- `python -m pytest -q tests\unit tests\domains\memory` -> 100 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase4_runtime.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 32 passed
- `$env:PYTHONPATH='src'; python src\apps\daemon\main.py --provider ollama --disable-tool-use --skip-desktop-mcp --healthcheck-deep --skip-llm-ping` -> passed
- `$env:PYTHONPATH='src'; python src\apps\daemon\main.py --provider ollama --disable-tool-use --skip-desktop-mcp --healthcheck-deep --skip-llm-ping --feishu-enable` -> passed，`feishu_config=configured`
- `.\yunxi.cmd --status` -> passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k ollama` -> 2 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k moonshot` -> 2 passed
- `python -m pytest -q tests\integration\test_moonshot_cloud_matrix.py -m real_llm` -> 6 passed
- `python -m pytest -q tests\integration\test_daily_mode_feishu_live.py -m "real_llm and feishu_live"` -> 1 skipped（未设置 `FEISHU_LIVE_TEST=1`，未误发真实消息）

### 下一步

进入飞书日常模拟测试。建议顺序：
1. 先开启 `FEISHU_LIVE_TEST=1` 跑现有飞书 live 主动发送测试，确认真实发送链路。
2. 再启动 daemon `--feishu-enable`，手动向云汐发普通消息，确认收消息、Runtime 回复和飞书回发。
3. 触发一个需要确认的工具请求，通过飞书回复“确认/取消”，验证 pending tool confirmation 闭环。
4. 让 Presence 主动 tick 真实发一条主动消息，验证日常模式主动触达。

---

## [2026-04-16] 飞书日常模拟测试：主动发送、收发消息和工具确认闭环通过

**状态**：已完成首轮飞书真实日常模拟测试。飞书现在可以作为日常模式唯一对话入口继续推进。

### 测试结果

- 飞书 live 主动发送：
  - 普通沙箱首次运行因网络 socket 权限失败，外部权限重跑通过。
  - `FEISHU_LIVE_TEST=1 python -m pytest -q tests\integration\test_daily_mode_feishu_live.py -m "real_llm and feishu_live"` -> 1 passed。
- 飞书 daemon 普通文本收发：
  - 启动参数：`--provider moonshot --feishu-enable --disable-tool-use --skip-desktop-mcp --embedding-provider lexical --tick-interval 9999 --run-seconds 180`。
  - 飞书真实文本“云汐，收到吗”被 daemon 捕获：输出出现 `[飞书] 收到消息 from ...: 云汐，收到吗`。
  - 说明 WebSocket 接收、线程回调、Runtime 调用和飞书回复路径进入真实链路。
- 飞书工具确认闭环：
  - 启动参数：`--provider moonshot --feishu-enable --embedding-provider lexical --tick-interval 9999 --run-seconds 240`。
  - 用户通过飞书发送“帮我把 yunxi live clipboard test 复制到剪贴板”。
  - daemon 捕获工具请求和后续“确认”。
  - Desktop MCP 输出 `ListToolsRequest` 和 `CallToolRequest`。
  - `Get-Clipboard` -> `yunxi live clipboard test`。
  - 结论：飞书发起工具请求、云汐要求确认、飞书回复确认、Desktop MCP 执行写剪贴板真实闭环通过。

### 期间发现并修复

- `lark-oapi` WebSocket 使用模块级全局 event loop。前一次真实 daemon 接收测试报错：`This event loop is already running`。
- 修复 `FeishuWebSocket`：
  - WebSocket 线程内创建独立 event loop，并临时绑定到 `lark_oapi.ws.client.loop`。
  - stop 时使用实例持有的 loop 做 `_disconnect()`。
  - 关闭 loop 前取消 pending tasks，减少退出时 `Task was destroyed but it is pending` 告警。
- daemon 新增 `--run-seconds`，用于 live 验收时有界运行并自动退出。
- daemon 飞书回调增加收到消息的 console 打印，便于 live 验收定位。

### 已验证

- `python -m py_compile src\interfaces\feishu\websocket.py tests\unit\test_feishu_websocket.py src\apps\daemon\main.py` -> passed
- `python -m pytest -q tests\unit\test_feishu_websocket.py tests\unit\test_daemon_healthcheck.py tests\unit\test_feishu_adapter.py` -> 13 passed
- `python -m pytest -q tests\unit\test_feishu_websocket.py tests\unit\test_daemon_healthcheck.py tests\unit\test_feishu_adapter.py tests\integration\test_phase5_daily_mode.py` -> 18 passed
- `FEISHU_LIVE_TEST=1 python -m pytest -q tests\integration\test_daily_mode_feishu_live.py -m "real_llm and feishu_live"` -> 1 passed

### 剩余风险

- `lark-oapi` 对 `im.chat.access_event.bot_p2p_chat_entered_v1` 和 `im.message.message_read_v1` 会输出 `processor not found`，目前不影响文本消息接收和回复，但后续可增加空 handler 降低噪声。
- 本轮确认工具使用剪贴板写入作为样例；其他 Desktop MCP 工具仍需逐项 live 验收。

---

## [2026-04-16] Desktop MCP 工具逐项直接对话验证

**状态**：首轮逐项验证通过。飞书链路已被前一轮验证，因此本轮直接模拟“用户发消息”和“用户回复确认”，走 `YunxiExecutionEngine` 的 pending confirmation 逻辑，不再手动通过飞书逐条交互。

### 新增验证

- 新增 `tests/integration/test_daily_mode_desktop_tools_direct.py`：
  - 使用真实 Desktop MCP server。
  - 使用脚本化 LLM 触发指定 tool call。
  - 第一轮 `engine.respond()` 模拟用户提出工具请求。
  - 第二轮 `engine.respond("确认")` 模拟用户确认。
  - 检查自然确认话术、工具执行结果和真实副作用。
- 覆盖工具：
  - `clipboard_write` + `clipboard_read`：写入并读取 `yunxi direct clipboard matrix`。
  - `screenshot_capture`：保存真实截图文件并检查文件非空。
  - `desktop_notify`：发送桌面通知。
  - `app_launch_ui`：启动 Notepad。
  - `window_focus_ui`：聚焦 Notepad。
  - `window_minimize_ui`：最小化 Notepad。

### 期间发现并修复

- `desktop_notify` 原先依赖未安装的 `win10toast`，工具实际返回 `[错误：未安装 win10toast，无法发送通知]`，但 Engine 会继续给自然成功回复，容易掩盖工具失败。
- 修复 `desktop_notify`：
  - 保留 `win10toast` 优先路径。
  - 缺少 `win10toast` 或调用失败时，改用无第三方依赖的 PowerShell `System.Windows.Forms.NotifyIcon` fallback。
- 测试加强：
  - 不只检查云汐自然回复，还读取 Engine 上下文中的 `ToolResultContentBlock`。
  - 拦截 `[错误]`、`失败`、`未找到` 等实际工具失败结果。
- Notepad 窗口关键词在当前系统中应使用 `Notepad`，不是中文“记事本”。

### 已验证

- `python -m py_compile src\core\mcp\servers\desktop_server.py tests\integration\test_daily_mode_desktop_tools_direct.py` -> passed
- 普通沙箱运行 direct desktop matrix 因 Windows named pipe 权限失败，外部权限重跑：
  - `python -m pytest -q tests\integration\test_daily_mode_desktop_tools_direct.py -m desktop_mcp` -> 4 passed
- 既有 Desktop MCP 回归：
  - `python -m pytest -q tests\integration\test_mcp_desktop.py -m desktop_mcp` -> 5 passed
- Engine / MCPHub stage 4 回归：
  - `python -m pytest -q tests\unit\test_execution_engine_stage4.py tests\unit\test_mcp_hub_stage4.py` -> 6 passed

### 结论

当前 Desktop MCP 工具已经具备一条可重复的直接日常模式验收路径：不依赖飞书手工交互，也不绕过云汐的确认协议。后续新增工具应先加入该矩阵，再做飞书 live 抽样。

---

## [2026-04-16] 阶段 4 完成：日常工具确认和错误人格化

**状态**：已完成首版。阶段 4 目标是让 daily_mode 下工具请求不再直接变成安全错误，并避免把工程异常暴露给用户。

### 完成内容

- 新增 pending tool confirmation 最小闭环：
  - `MCPHub` 在安全策略返回 `ask` 时创建 `PendingToolConfirmation`，不直接执行工具。
  - `YunxiExecutionEngine` 会自然告知“这一步需要你点头”，用户回复“确认/同意/可以/继续/ok”等后继续执行最新 pending 工具。
  - 用户回复“取消/不要/先别”等会放弃 pending 工具。
- 工具失败和 Engine 异常用户可见人格化：
  - 移除用户可见的 `[云汐这里出了点小问题：...]`、`[工具执行遇到问题...]`、`[尝试使用工具多次仍未完成]`。
  - 技术细节保留在 `ExecutionResult.error` 和日志，不直接进入回复文本。
- MCP 失败结构化：
  - 未知工具不再 raise 绕过审计，改为 `error_type="unknown_tool"` 的结构化结果。
  - `MCPClient` 对 connect / initialize / list_tools / call_tool 增加 `asyncio.wait_for()` timeout。
- LLM provider 增加 typed errors 和重试：
  - 新增 `LLMProviderNetworkError`、`LLMProviderHTTPError`、`LLMProviderResponseError`。
  - provider 请求按 `max_retries` 重试，网络/超时/可重试 HTTP 错误进入结构化异常。
- 技能快速路径不再直接固定话术收尾：
  - 快捷技能执行后会把结果交给 LLM 做最终自然表达。
  - 如果最终表达失败，才回退到人格化的保守回复。

### 已验证

- `python -m py_compile src\core\execution\engine.py src\core\mcp\hub.py src\core\mcp\client.py src\core\llm\provider.py src\core\llm\__init__.py tests\unit\test_mcp_hub_stage4.py tests\unit\test_execution_engine_stage4.py tests\unit\test_llm_provider_errors.py tests\integration\test_mcp_desktop.py` -> passed
- `python -m pytest -q tests\unit\test_mcp_hub_stage4.py tests\unit\test_execution_engine_stage4.py tests\unit\test_llm_provider_errors.py tests\unit\test_execution_engine.py` -> 12 passed
- `python -m pytest -q tests\unit tests\domains\memory` -> 92 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase4_runtime.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 30 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k ollama` -> 2 passed（真实本地 Ollama）
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k moonshot` -> 2 passed（真实 Moonshot，需要联网）
- `python -m pytest -q tests\integration\test_moonshot_cloud_matrix.py -m real_llm` -> 6 passed（真实 Moonshot，需要联网）
- `python -m pytest -q tests\integration\test_mcp_desktop.py -m desktop_mcp` -> 普通沙箱因 Windows named pipe 权限失败；外部权限重跑 5 passed

### 下一步

进入阶段 5：飞书真实日常入口、Tray/WebUI 状态控制面板和分层感知。

优先处理：
1. Perception provider 分层，基础感知、慢速外部感知、可选隐私感知分别带 timeout 和降级。
2. 飞书 live 接入 pending confirmation，完成日常聊天、主动消息和工具确认闭环。
3. 常驻 daemon 增加深度 healthcheck。
4. Tray/WebUI 简化为状态、日志、healthcheck 和工厂模式控制入口。

---

## [2026-04-16] 阶段 3 完成：主动预算、长期关系记忆和连续性沉淀

**状态**：已完成首版。阶段 3 目标是让云汐的主动性和长期关系状态不再只依赖进程内临时变量。

### 完成内容

- `CompanionContinuityService` 新增 `proactive_count_date`：
  - `recent_proactive_count` 按本地日期归属。
  - `InitiativeEngine.evaluate()` 前会刷新日期，跨天自动恢复主动预算。
- `MemoryManager` 新增持久化关系记忆：
  - 偏好、共同经历、承诺写入 `relationship_memory.json`。
  - 重建 `MemoryManager` 后可恢复关系记忆并进入 prompt summary。
  - 新增 `MemoryManager.close()`，统一关闭 PatternMiner 和 SkillLibrary 资源。
- 普通聊天后新增保守连续性抽取：
  - 用户提到偏好、承诺、共同经历时写入长期记忆。
  - 用户提到“明天/下次/之后继续/提醒/跟进”等内容时写入 open thread 和 proactive cue。
  - 用户表达疲惫、压力、失眠等状态时设置 `comfort_needed`；工作相关消息设置 `task_focus`。
- 主动事件 `affect_delta` 现在真实影响 HeartLake：
  - 事件选中后按 valence/arousal 调整安全感、想念值和主导情绪。
  - 选中的主动事件写入 continuity 的 `initiative_events`，后续 prompt summary 可看到近期主动素材。
- Runtime/daemon 生命周期补齐：
  - `YunxiRuntime.chat()` 在普通对话结束后沉淀关系记忆和连续性线索。
  - `close_runtime()` 调用 `runtime.memory.close()`。

### 已验证

- `python -m py_compile src\core\initiative\continuity.py src\domains\memory\manager.py src\core\runtime.py src\core\cognition\heart_lake\core.py src\core\cognition\initiative_engine\engine.py src\apps\daemon\main.py tests\unit\test_continuity_persistence.py tests\unit\test_initiative_engine.py tests\domains\memory\test_relationship_memory.py tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase4_runtime.py tests\integration\daily_mode_scenario_tester.py` -> passed
- `python -m pytest -q tests\unit\test_continuity_persistence.py tests\unit\test_initiative_engine.py tests\domains\memory\test_relationship_memory.py tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase4_runtime.py` -> 29 passed
- `python -m pytest -q tests\unit tests\domains\memory` -> 85 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase4_runtime.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 30 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k ollama` -> 2 passed（真实本地 Ollama）
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k moonshot` -> 2 passed（真实 Moonshot，需要联网）
- `python -m pytest -q tests\integration\test_moonshot_cloud_matrix.py -m real_llm` -> 6 passed（真实 Moonshot，需要联网）

### 下一步

进入阶段 4：日常工具确认和用户可见错误人格化。

优先处理：
1. 实现统一 pending tool confirmation 协议。
2. LLM 异常、工具异常、安全 ask、未知工具都转为云汐人格化表达，技术细节只进日志。
3. 技能快速路径执行结果回到 LLM 做最终自然表达。
4. LLM provider 增加错误类型、重试和可观测日志。
5. MCP connect/list_tools/call_tool 增加 timeout 和结构化失败审计。

---

## [2026-04-16] 阶段 2 完成：Runtime 单入口、飞书通道和常驻稳定性

**状态**：已完成。阶段 2 目标是让真实入口不会因为线程、并发和同步发送阻塞破坏日常模式运行。

### 完成内容

- `YunxiRuntime` 新增单入口 `asyncio.Lock`，串行化 `chat()` 和 `proactive_tick()`，避免飞书消息、Presence 主动 tick、未来 Tray/WebUI 并发污染 `ExecutionEngine.context`、`HeartLake` 和 `Continuity`。
- `FeishuAdapter` 支持绑定 daemon 主 asyncio loop：
  - WebSocket 线程回调通过 `asyncio.run_coroutine_threadsafe()` 投递到主 loop。
  - 同一 loop 内调用时使用 `create_task()`。
  - 处理任务/future 异常会写日志，不再静默丢失。
- 飞书发送链路改为 `asyncio.to_thread()` 包装同步 `requests`：
  - 被动回复发送不阻塞主事件循环。
  - 主动消息发送仍有锁，避免同一入口并发发送。
  - 错误回复发送失败时只记日志，不反向打断 Runtime。
- `FeishuWebSocket.stop()` 完成实际关闭流程：
  - 优先调用底层 client 的 `stop()` / `close()`。
  - 对 lark client 尝试调用私有 `_disconnect()` 并停止其 event loop。
  - join WebSocket 线程，超时后写 warning。
- 补齐飞书真实消息边界：
  - 支持 `FEISHU_IGNORE_SENDER_IDS` / 构造参数忽略指定 sender，避免自消息循环。
  - 消息去重从整表清空改为 TTL + LRU。
  - daemon 顶部不再导入飞书模块，只有 `--feishu-enable` 分支才加载 `lark-oapi` 相关依赖。

### 已验证

- `python -m py_compile src\core\runtime.py src\interfaces\feishu\adapter.py src\interfaces\feishu\websocket.py src\apps\daemon\main.py tests\unit\test_feishu_adapter.py tests\unit\test_feishu_websocket.py tests\integration\test_phase4_runtime.py` -> passed
- `python -m pytest -q tests\unit\test_feishu_adapter.py tests\unit\test_feishu_websocket.py tests\integration\test_phase4_runtime.py` -> 13 passed
- `python -m pytest -q tests\unit` -> 56 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 22 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k ollama` -> 2 passed（真实本地 Ollama）
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k moonshot` -> 2 passed（真实 Moonshot，需要联网）
- `python -m pytest -q tests\integration\test_daily_mode_feishu_live.py -m "real_llm and feishu_live"` -> 1 skipped（未设置 `FEISHU_LIVE_TEST=1`，未误发真实消息）

### 下一步

进入阶段 3：主动性、长期关系记忆和连续性沉淀。

优先处理：
1. `recent_proactive_count` 改为按日期统计，跨天自动重置。
2. 偏好、共同经历、承诺从进程内列表改为持久化关系记忆。
3. 主动事件被选中后，将 `affect_delta` 应用到 HeartLake，并写入 continuity。
4. 普通聊天后自动抽取 open_threads、proactive_cues、偏好和承诺。
5. 补 `MemoryManager.close()`，统一关闭 PatternMiner / SkillLibrary / embedding 资源。

---

## [2026-04-16] 完成：迁移 2.0 反应库为日常模式表达参考

**状态**：已完成首版并通过本地真实 LLM 回归。用户反馈“针对我说话反应”仍显得规则化、死板；排查确认 3.0 当前回复生成虽走 LLM，但情绪表达指引主要依赖 `HeartLakeUpdater` 的规则触发和 `YunxiPromptBuilder._build_emotion_section()` 的少量硬编码提示。

### 完成内容

- 从 `D:\yunxi2.0\data\persona\reaction_library.json` 迁移反应库思路，但不直接搬运原始内容。
- 新增 `data/persona/reaction_library.json`：
  - 保留问候、想念、安慰、鼓励、玩笑、庆祝、修复、工作、夜间陪伴、轻微吃醋等日常反应类型。
  - 移除原库中高亲密成人条目，并改写亲密/夜间类示例，确保默认日常模式不注入露骨内容。
- 新增 `core.persona.reaction_library`：
  - 负责加载结构化反应库。
  - 按本轮用户输入和当前情绪检索反应参考。
  - 输出只作为 LLM 表达姿态素材，不作为固定模板回复。
- `RuntimeContext` 新增 `user_input`，`YunxiRuntime.chat()` 会把本轮用户输入传给 PromptBuilder。
- `YunxiPromptBuilder` 新增【当前反应参考】section：
  - 写入匹配场景、风格和少量表达温度参考。
  - 明确要求“不要照抄示例、不要输出内部字段/触发词/匹配分数”。

### 已验证

- `python -m py_compile src\core\persona\reaction_library.py src\core\prompt_builder.py src\core\runtime.py tests\unit\test_reaction_library.py tests\unit\test_prompt_builder.py tests\integration\test_daily_mode_scenario_tester.py` -> passed
- `python -m pytest -q tests\unit\test_reaction_library.py tests\unit\test_prompt_builder.py` -> 12 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 22 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k ollama` -> 2 passed（真实本地 Ollama）
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k moonshot` -> 2 passed（真实 Moonshot，需要联网）
- `python -m pytest -q tests\integration\test_moonshot_cloud_matrix.py -m real_llm` -> 6 passed（真实 Moonshot，需要联网）

---

## [2026-04-16] 阶段 1 完成：恢复日常模式验收可信度

**状态**：已完成。阶段 1 的目标是让日常模式验收真正跑到 Runtime/LLM/daemon 稳定性逻辑，而不是卡在 fixture、真实桌面感知或脆弱关键词断言上。

### 完成内容

- 修复 `tests/integration/test_moonshot_cloud_matrix.py`：
  - 不再写入空事件库 `[]`，改为使用真实 `data/initiative/life_events.json`，缺失时才写入最小有效事件库。
  - 使用 `StaticPerceptionProvider`，避免云端 LLM 验收触发真实 Windows 桌面感知。
  - open thread 场景补足触发条件，确保测试实际进入主动生成路径。
  - 复用 `DailyModeScenarioTester.behavior_check()`，统一检查工程错误模板、内部字段、工具化表达和伴侣感。
- 修复 `tests/integration/test_daemon_stability.py`：
  - 使用 `StaticPerceptionProvider`，稳定性测试不再读取真实前台窗口/idle/CPU。
  - 保留真实 continuity 持久化、多轮 chat、主动 tick、上下文限制等 daemon 稳定性覆盖。
- 增强 `DailyModeScenarioTester.behavior_check()`：
  - 新增 `<think>` / `</think>` 内部推理泄露检查。
  - 新增工程错误模板拦截，避免 `[云汐这里出了点小问题：...]`、`All connection attempts failed` 被误判为合格回复。
  - 扩展伴侣语气 token，减少真实 LLM 同义表达造成的误杀。
- 调整 `test_daily_mode_full_simulation_real_llm.py`：
  - 本地 Ollama 记忆/陪伴场景长度上限从 260 调整为 360，仍保留长度边界，但不把正常本地模型长一点的自然回复误判为失败。

### 已验证

- `python -m py_compile tests\integration\daily_mode_scenario_tester.py tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_daily_mode_full_simulation_real_llm.py tests\integration\test_moonshot_cloud_matrix.py tests\integration\test_daemon_stability.py` -> passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 21 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k ollama` -> 2 passed（真实本地 Ollama）
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k moonshot` -> 2 passed（真实 Moonshot，需要联网）
- `python -m pytest -q tests\integration\test_moonshot_cloud_matrix.py -m real_llm` -> 6 passed（真实 Moonshot，需要联网）

### 重要说明

- 普通沙箱网络下 Moonshot 会被拦截，`ExecutionEngine` 当前会把连接异常包装成用户可见错误文本。行为检查器已经能识别这种工程错误模板，避免测试误通过。
- 这次没有修复用户可见错误人格化本身；该问题仍归入阶段 4 的 P0-10。

### 下一步

进入阶段 2：修 Runtime 单入口、飞书通道和常驻稳定性。

优先处理：
1. 飞书 WebSocket 线程回调安全投递到主 asyncio loop。
2. Runtime 增加单入口异步锁或事件队列。
3. 飞书发送链路 async 化或 `asyncio.to_thread()` 包装。
4. `FeishuWebSocket.stop()` 完成真实关闭和线程 join。
5. 增加飞书桥接测试和 Runtime 并发测试。

---

## [2026-04-16] 阶段 0 完成：冻结日常模式验收口径

**状态**：已完成。阶段 0 的目标是冻结“日常模式必须按亲密伴侣体验验收”的口径，并确认 `DailyModeScenarioTester` 作为后续修复的主验收框架可用。

### 完成内容

- 明确后续修复继续围绕日常模式完善规划推进，不进入 Phase 6 工厂模式。
- 保持 `DailyModeScenarioTester` 为日常模式主验收框架。
- 补齐行为检查器的过长输出回归断言，确保阶段 0 通过标准覆盖内部字段泄露、工具化表达和过长输出。
- 确认 mock 只用于框架自测，不能替代真实 LLM 日常模式完成结论。

### 已验证

- `python -m py_compile tests\integration\daily_mode_scenario_tester.py tests\integration\test_daily_mode_scenario_tester.py` -> passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py` -> 5 passed

### 下一步

进入阶段 1：恢复验收可信度。

优先处理：
1. 修复或迁移 `test_moonshot_cloud_matrix.py`，解决空事件库导致未真正调用 Moonshot 的问题。
2. 修复 `test_daemon_stability.py` 使用真实感知导致挂起的问题，改用 static/mock perception provider。
3. 重跑本地 Ollama 与 Moonshot 的 Layer 2 日常仿真，并只把真实通过结果写入日志。

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

1. 修复旧 `test_moonshot_cloud_matrix.py` 空事件库问题，并迁移到 `DailyModeScenarioTester`。（阶段 1 已修复空事件库，并复用统一行为检查器）
2. 修复 daemon stability 测试挂起问题，并复用新的 static perception provider。（阶段 1 已完成）
3. 新增重启后记忆持久化测试，目前预计会暴露 `MemoryManager` 长期关系记忆不足。
4. 新增主动预算跨日重置测试，目前预计会暴露 `recent_proactive_count` 不按日期重置。
5. 新增飞书线程回调测试，目前预计会暴露 `asyncio.create_task()` 在线程中无 event loop 的问题。

---

## 当前总状态

**日期**：2026-04-16  
**阶段**：Phase 5 日常模式硬化中，尚不应进入 Phase 6 工厂模式。  
**本次动作**：阶段 4 已完成，入口设计已调整为飞书唯一日常对话通道；下一步进入飞书 live、Tray/WebUI 状态控制面板和分层感知。

### 当前结论

- Phase 0-5 的骨架已经基本搭好：Runtime、PromptBuilder、LLMAdapter、MCPHub、Memory、HeartLake、Initiative、Presence、daemon、飞书通道、Ollama/Moonshot 接入均已有实现。
- yunxi2.0 的关键资产已经迁入一部分：人格 profile、用户关系 profile、生活事件库、三层主动事件系统、表达上下文、continuity/open_threads。
- 日常模式仍不能标记为完成。阶段 1 已恢复本地 Ollama、Moonshot 和 daemon stability 的基础验收可信度；阶段 2 已修复 Runtime 单入口、飞书线程回调、飞书异步发送和 WebSocket 停止流程；阶段 3 已补齐主动预算跨日重置、关系记忆持久化、连续性自动沉淀和主动事件情绪影响；阶段 4 已完成工具确认最小闭环、错误人格化、provider 重试和 MCP timeout/结构化失败。
- 旧日志中“P0-E 全部完成”的表述已作废。当前真实 LLM 第一批仿真、Moonshot 旧矩阵和 Desktop MCP 集成均已通过；剩余阻塞集中在飞书真实入口闭环、Tray/WebUI 状态控制面板、分层感知和深度 healthcheck。

### 进入工厂模式前的硬门槛

1. 日常模式真实 LLM 验收必须同时覆盖本地 Ollama 和云端 Moonshot，并实际跑通。
2. 飞书作为唯一日常对话入口，必须能稳定接收用户消息、调用 Runtime、返回回复、发送主动消息，并完成工具确认。
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
- 当前问题：飞书 live 还未完成完整真实入口验收；Tray/WebUI 仍只是状态快照适配，尚未成为状态与控制面板；分层感知和 deep healthcheck 仍待补齐。

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

当前状态：阶段 1 已修复。旧矩阵现在使用真实事件库、static perception provider 和统一行为检查器；真实 Moonshot 运行结果为 6 passed。

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

当前状态：阶段 1 已修复。稳定性测试已改用 static perception provider；本地非 real_llm 回归中该文件 7 passed。

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

当前状态：阶段 2 已修复。`FeishuAdapter` 支持绑定主 loop；WebSocket 线程回调通过 `run_coroutine_threadsafe()` 投递；`tests/unit/test_feishu_adapter.py` 覆盖线程回调进入主 loop 并调用 `runtime.chat()`。

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

当前状态：阶段 2 已修复。`YunxiRuntime` 使用单入口 `asyncio.Lock` 串行化 `chat()` 和 `proactive_tick()`；`tests/integration/test_phase4_runtime.py` 覆盖并发 chat、chat + proactive tick 不重入 LLM。

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

当前状态：阶段 3 已修复。`CompanionContinuityService` 新增 `proactive_count_date`，`InitiativeEngine.evaluate()` 前刷新日期；跨日后 `recent_proactive_count` 自动归零并恢复主动预算。

### P0-06：日常工具的安全确认链路没有闭合

文件：`src/core/mcp/security.py`、`src/core/mcp/hub.py`、`src/core/execution/engine.py`

问题：
- daily_mode 下 WRITE / EXECUTE 默认返回 `ask`。
- `MCPHub` 对 `ask` 的处理只是返回错误。
- 已有对话内 pending confirmation 最小闭环，但飞书 live 尚未完成确认/取消的真实入口验收。

影响：
- 云汐 prompt 里说“可以使用工具”，但实际调用会失败。
- 用户体验会变成“云汐想帮忙但总是说失败”。

修复要求：
- 设计统一确认协议：pending tool request。
- 飞书真实入口必须能完成确认/取消；WebUI/Tray 只展示 pending 状态，不作为正式确认入口。
- LLM 回复要自然表达“这个操作需要你点头”，不能暴露安全策略字段。

当前状态：阶段 4 已完成最小闭环。`MCPHub` 会为 `ask` 生成 pending confirmation，`YunxiExecutionEngine` 支持“确认/取消”继续或放弃最新 pending 工具；回复采用自然表达，不暴露安全策略字段。阶段 5 需要把确认/取消接入飞书 live；Tray/WebUI 只负责状态展示。

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

当前状态：阶段 3 已完成首版持久化和保守抽取。`MemoryManager` 将偏好、共同经历、承诺落盘到 `relationship_memory.json`，重建后可恢复；普通聊天后会保守抽取偏好/承诺/经历。周期性 LLM 摘要更新仍留作后续增强。

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

当前状态：阶段 2 已修复主链路。`FeishuAdapter.handle_message()` 和 `send_proactive_message()` 已用 `asyncio.to_thread()` 包装同步发送；发送异常只写日志，不反向打断 Runtime。

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

当前状态：阶段 2 已修复。`FeishuWebSocket.stop()` 会调用底层 client stop/close 或 lark `_disconnect()`，随后 join 线程并对超时写 warning；单元测试覆盖 stop 关闭 client 并回收线程。

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

当前状态：阶段 4 已修复。Engine 不再返回括号化工程错误；LLM 异常、工具失败、max turns、确认取消和未知工具均有自然回复或结构化内部错误，技术细节只进入 error/log/audit。

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

当前状态：阶段 3 已修复。主动事件选中后会调用 `HeartLake.apply_affect_delta()`，并把事件 id/category/seed/affect 写入 continuity 的 `initiative_events`。

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

当前状态：阶段 3 已完成保守规则版。普通聊天后会抽取未来提醒/继续话题为 open thread 和 proactive cue，并抽取偏好/承诺/经历进入长期关系记忆。

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

当前状态：阶段 4 已修复首版。技能快速路径执行结果会交给 LLM 做最终自然表达；最终表达失败时才使用人格化保守回退。

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

### P1-07：Tray/WebUI 定位需改为状态与控制面板

文件：`src/apps/tray/web_server.py`

问题：
- 当前只有 `RuntimeStatus` 和 `build_runtime_status()`。
- 原设计把 WebUI/Tray 也当作聊天和主动消息入口，和飞书职责重叠。
- 还没有真实托盘图标、Web server、日志查看、healthcheck 操作、飞书连接状态展示和工厂模式入口。

影响：
- 多个聊天入口会放大并发、消息去重、工具确认和状态同步复杂度。
- WebUI/Tray 如果做重，会拖慢阶段 5 的核心目标：打穿飞书真实日常入口。

修复方向：
- 飞书作为唯一日常对话入口：用户消息、云汐主动消息、工具确认全部走飞书。
- WebUI 只做状态、日志、healthcheck、飞书连接状态、pending confirmation 状态展示和工厂模式入口。
- Tray 左键打开 WebUI；右键提供打开状态页、进入工厂模式、执行 healthcheck、打开日志、停止/重启 daemon 等控制项。

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

当前状态：阶段 4 已修复主路径。provider 新增网络/HTTP/响应三类结构化错误，并对 complete 请求按 `max_retries` 重试；stream 路径仍留作后续细化。

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

当前状态：阶段 4 已修复。`MCPClient` 对 connect/initialize/list_tools/call_tool 增加 timeout；未知工具返回 `error_type="unknown_tool"` 的结构化结果并进入审计，不再直接 raise。

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

当前状态：阶段 2 已修复本阶段边界项。`FeishuWebSocket` 支持忽略指定 sender，去重改为 TTL/LRU；daemon 飞书导入已延迟到 `--feishu-enable` 分支。`transport` 字段和 `proactive_callback` 参数清理仍作为后续低优先级接口整理。

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

当前状态：阶段 3 已完成主生命周期。`MemoryManager.close()` 已统一关闭 PatternMiner 和 SkillLibrary，daemon close 和 DailyModeScenarioTester teardown 已调用。Ollama embedding 的 sync/async client 结构仍留作后续细化。

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
- 工具确认测试：写剪贴板/启动应用进入 pending confirmation，经飞书真实入口确认后继续执行。
- 错误人格化测试：LLM 异常、工具异常、安全 ask、未知工具都返回自然表达。
- provider 重试测试：临时网络错误触发重试，最终失败时错误类型可区分。

必须验证：
- Layer 2/3/4 继续通过。
- 工具确认链路通过飞书真实入口闭合。

通过后可以进入：
- 阶段 5 的飞书 live 入口、WebUI/Tray 状态控制面板和感知增强。

### 阶段 5：补飞书真实日常入口、Tray/WebUI 状态控制面板和分层感知

先修问题：
- P1-06：Perception provider 分层，基础感知、慢速外部感知、可选隐私感知分别带 timeout 和降级。
- P1-07：飞书作为唯一日常对话入口，完成收消息、Runtime 回复、主动消息发送、工具确认确认/取消闭环。
- P1-07：WebUI/Tray 简化为状态与控制面板，支持状态查看、运行日志、healthcheck、飞书连接状态、pending confirmation 状态展示和工厂模式入口。
- P2-05：增加 `--healthcheck-deep`，覆盖 LLM ping、memory init/close、event library、continuity read/write、optional feishu config。
- P2-04：把 `data/relationship/user_profile.md` 改成真实中文 Markdown，保留转义加载兼容。
- P2-01 / P2-02：逐步用 dataclass / Protocol / TypedDict 替换核心裸 `Any` / `Dict`，并减少宽泛异常。

原因：
- 日常聊天统一走飞书，避免 WebUI/Tray/飞书多个入口重复承载对话造成并发、去重和确认链路复杂化。
- WebUI/Tray 的价值是本地可观测和控制，不是再造一套聊天产品。
- 感知太薄会削弱“住在电脑里”的真实感，但感知增强必须先有超时、隐私和降级边界。

必须新增/修复测试：
- 飞书 live smoke test：能收用户消息、返回 Runtime 回复、发送主动消息、通过“确认/取消”处理 pending 工具。
- WebUI/Tray smoke test：能显示状态、日志、飞书连接状态、pending confirmation 状态，并能触发 healthcheck / 工厂模式入口。
- deep healthcheck 测试：能发现 LLM、memory、event library、continuity 和飞书配置问题。
- 感知 timeout 测试：慢 provider 不阻塞整轮聊天。

必须验证：
- 日常模式全量仿真矩阵通过。
- daemon 短跑/长跑稳定性通过。
- 飞书真实入口完成 chat + 主动消息 + 工具确认。
- `yunxi` CLI 工厂模式入口占位可从任意项目目录解析当前路径。

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
