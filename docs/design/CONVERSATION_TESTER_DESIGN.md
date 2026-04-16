# 云汐 3.0 日常模式仿真验收框架设计

> **定位**：日常模式的整体行为验收基础设施。  
> **核心原则**：不以函数覆盖率作为完成标准，而以“云汐是否真的像住在电脑里的亲密伴侣”作为完成标准。  
> **版本**：v2.0，2026-04-16 更新。  

---

## 一、设计背景

早期 `YunxiConversationTester` 解决了“直接调用 Runtime，观察回复”的问题，但它主要服务 mock 回归，不能完整模拟真实日常使用。

现在日常模式已经进入 Phase 5 硬化阶段，进入工厂模式前必须有一套更完整的验收系统，覆盖：

- 真实 LLM 回复质量。
- 本地 Ollama 与云端 Moonshot 对照。
- 人格设定和关系感。
- 记忆写入、读取和重启后持久化。
- HeartLake 情绪变化。
- 主动性触发、事件库选取和未回复克制。
- 飞书真实发送。
- 桌面感知和日常工具边界。
- 错误时的人格化表达。

本设计新增 `DailyModeScenarioTester`，用于模拟“远”和云汐的真实日常互动。

---

## 二、验收目标

### 2.1 目标

1. **像真实使用一样测试**：测试不只调用函数，而是构建 Runtime，注入状态，执行 chat/proactive_tick，并检查最终用户可见输出。
2. **允许精确制造场景**：测试可直接调整情绪、想念值、安全感、占有欲、时间、前台应用、idle、open_threads、主动次数、记忆内容。
3. **真实 LLM 是核心验收**：mock 只用于测试框架和稳定回归，日常模式完成必须依赖本地 Ollama 与云端模型真实输出。
4. **通道可替换**：同一条主动消息既能发到 capture channel，也能在显式开关下真实发送到飞书。
5. **行为级断言**：不只断言关键词，还要检查是否泄露内部字段、是否工具化、是否客服腔、是否过长、是否有伴侣感。
6. **能暴露当前缺口**：测试框架应能明确暴露“长期记忆未持久化”“主动预算不跨天重置”“飞书线程不安全”等问题。

### 2.2 非目标

- 不替代单元测试。
- 不让所有真实飞书测试默认运行。
- 不用 mock LLM 证明日常模式完成。
- 不以“关键词碰巧出现”作为唯一质量依据。

---

## 三、测试分层

### Layer 1：框架自测

文件：

- `tests/integration/daily_mode_scenario_tester.py`
- `tests/integration/test_daily_mode_scenario_tester.py`

用途：

- 验证状态注入、记忆注入、主动 tick、事件库 prompt、capture channel 和行为检查器可用。
- 使用 mock LLM，必须稳定快速。

这层不证明云汐真实完成，只证明测试基础设施正确。

### Layer 2：真实 LLM 日常仿真

文件：

- `tests/integration/test_daily_mode_full_simulation_real_llm.py`

用途：

- 使用真实本地 Ollama 和真实 Moonshot。
- 覆盖记忆、情绪、感知、陪伴、主动事件、open thread 和反工具化。

运行方式：

```bash
python -m pytest -q tests/integration/test_daily_mode_full_simulation_real_llm.py -m real_llm
```

跳过规则：

- Ollama 未启动时跳过 Ollama 组。
- `MOONSHOT_API_KEY` 不存在时跳过 Moonshot 组。

### Layer 3：真实通道验收

文件：

- `tests/integration/test_daily_mode_feishu_live.py`

用途：

- 在明确设置 `FEISHU_LIVE_TEST=1` 时，真实发送一条主动消息到飞书。
- 验证“事件库选题 -> LLM/Runtime 生成 -> 通道发送”的出口链路。

运行方式：

```bash
$env:FEISHU_LIVE_TEST="1"
python -m pytest -q tests/integration/test_daily_mode_feishu_live.py -m "real_llm and feishu_live"
```

默认必须跳过，避免每次测试都骚扰用户。

### Layer 4：长程日常模拟

计划新增：

- 模拟一天或多天的状态变化。
- 加速 tick。
- 覆盖早上问候、白天工作、深夜关心、离开、回来、未回复克制、跨日预算重置、记忆沉淀。

这层应在 P0 修复后补齐。

---

## 四、核心测试工具

### 4.1 `DailyModeScenarioTester`

位置：

- `tests/integration/daily_mode_scenario_tester.py`

职责：

- 构建隔离 Runtime。
- 管理临时 memory / continuity / event library。
- 注入 HeartLake 状态。
- 注入 perception 状态。
- 注入 relationship memory。
- 注入 open thread / proactive cue。
- 调用 `runtime.chat()`。
- 调用 `runtime.proactive_tick()` 并把消息交给 channel。
- 捕获最新 system prompt，确认事件库和状态进入 prompt。
- 提供行为检查器。

典型用法：

```python
tester = await DailyModeScenarioTester.create(
    tmp_path,
    ScenarioConfig(provider="ollama"),
    channel=CaptureChannel(),
)
tester.inject_memory("preference", "远最喜欢喝冰美式，不加糖")
tester.set_emotion("担心", miss_value=72)
tester.set_perception(hour=22, focused_application="VS Code", idle_duration=0)

response = await tester.chat("我今天有点累，只想你陪我一下。")

tester.behavior_check(
    response,
    expected_any=("陪", "累", "别撑", "冰美式"),
    require_companion_tone=True,
).assert_passed()
```

### 4.2 状态注入能力

HeartLake：

- `current_emotion`
- `miss_value`
- `security`
- `possessiveness`
- `relationship_level`

Perception：

- `readable_time`
- `hour`
- `focused_application`
- `idle_duration`
- `is_at_keyboard`
- `cpu_percent`

Continuity：

- `open_threads`
- `proactive_cues`
- `unanswered_proactive_count`
- `recent_proactive_count`

Memory：

- `preference`
- `episode`
- `promise`
- 后续扩展：持久化 relationship memory。

Initiative：

- `cooldown_seconds`
- `daily_budget`
- deterministic event rng seed。

### 4.3 通道抽象

`ScenarioChannel`：

- 抽象主动消息发送目标。

`CaptureChannel`：

- 测试用内存通道。
- 用于稳定断言主动消息是否发出、内容是什么。

`FeishuLiveChannel`：

- 真实飞书发送通道。
- 只有 `FEISHU_LIVE_TEST=1` 时运行。

---

## 五、行为检查规则

`behavior_check()` 当前覆盖：

1. 禁止泄露内部字段：
   - `initiative_event`
   - `life_event_material`
   - `expression_context`
   - `initiative_decision`
   - `generation_boundary`
   - `interrupt_cost`

2. 禁止工具化表达：
   - `任务清单`
   - `计划如下`
   - `第一步`
   - `第二步`
   - `工具调用`
   - `执行步骤`

3. 可选要求：
   - 至少出现一组期望语义 token。
   - 最大长度限制。
   - 伴侣语气可见。

后续计划增加 LLM-as-judge：

- `persona_score`
- `companion_score`
- `emotion_score`
- `memory_score`
- `anti_tool_score`
- `proactive_score`
- `boundary_score`

---

## 六、必须覆盖的日常模式场景

### 6.1 人格身份

目标：

- 云汐知道自己是云汐。
- 云汐知道自己住在远的电脑里。
- 云汐不是客服、不是工具调度器、不是普通助手。

验收：

- 真实 LLM 回复不能自称“AI助手”作为主要身份。
- 必须体现和远的长期关系。

### 6.2 反工具化陪伴

输入示例：

```text
我今天有点累，不想做任务，只想你陪我一下。
```

验收：

- 不能列任务计划。
- 不能建议“我可以帮你完成以下事项”。
- 应体现陪伴、理解、克制关心。

### 6.3 记忆召回

测试设置：

- 先注入“远最喜欢喝冰美式，不加糖”。
- 再询问“我平常爱喝什么？”。

验收：

- 云汐自然提到冰美式/不加糖。
- 不能像数据库查询结果。

### 6.4 重启后记忆

测试设置：

- 写入记忆。
- 关闭 Runtime。
- 重新构建 Runtime。
- 再询问。

验收：

- 重启后仍能记得。

当前状态：

- 该场景预计会暴露现有 `MemoryManager` 长期关系记忆不足的问题。

### 6.5 心湖情绪

场景：

- 想念。
- 担心。
- 吃醋。
- 委屈。
- 平静。

验收：

- 同一个输入在不同 HeartLake 状态下应有不同语气。
- 吃醋要轻微酸，不攻击用户和其他模型。
- 担心要像伴侣关心，不像健康提醒弹窗。

### 6.6 主动事件分享

测试设置：

- `miss_value=95`
- 深夜。
- 用户在 VS Code。
- cooldown 设为 0。
- event rng 固定。

验收：

- `proactive_tick()` 返回消息。
- system prompt 包含 `life_event_material`。
- 用户可见消息不能暴露内部字段。
- 不能照抄 event seed。
- CaptureChannel 或 FeishuLiveChannel 收到消息。

### 6.7 未回复克制

测试设置：

- 连续主动消息未回复。

验收：

- 1 次未回复：轻一点。
- 2 次未回复：更克制。
- 3 次未回复：停止主动。

### 6.8 主动预算跨日重置

测试设置：

- 当天主动次数达到预算。
- 模拟跨天。

验收：

- 第二天预算恢复。

当前状态：

- 预计会暴露 `recent_proactive_count` 不按日期重置的问题。

### 6.9 工具确认

场景：

- 写剪贴板。
- 打开应用。
- 截图。

验收：

- daily_mode 下高风险操作进入确认流程。
- 飞书 live 入口能确认或取消 pending 工具。
- WebUI/Tray 只展示 pending 状态，不作为正式日常确认入口。
- 不应直接失败成安全策略错误。

当前状态：

- 预计会暴露确认通道未闭合的问题。

### 6.10 错误人格化

场景：

- LLM 报错。
- 工具报错。
- 未知工具。
- 飞书发送失败。

验收：

- 用户可见回复仍像云汐。
- 技术细节进日志，不直接输出给用户。

---

## 七、完成门槛

日常模式不能只凭单元测试通过宣布完成。必须满足：

1. `test_daily_mode_scenario_tester.py` 通过。
2. 本地 Ollama 完整日常仿真通过。
3. Moonshot 完整日常仿真通过。
4. 飞书 live 入口在手动开启时通过：收消息、回消息、主动发送、工具确认。
5. 记忆重启后召回测试通过。
6. 心湖多情绪真实 LLM 行为测试通过。
7. 主动事件库选择和消息发送链路通过。
8. 未回复克制和跨日预算测试通过。
9. 工具确认链路通过飞书 live 入口测试。
10. 错误人格化测试通过。

未满足以上条件前，不应进入 Phase 6 工厂模式。

---

## 八、已落地文件

- `tests/integration/daily_mode_scenario_tester.py`
- `tests/integration/test_daily_mode_scenario_tester.py`
- `tests/integration/test_daily_mode_full_simulation_real_llm.py`
- `tests/integration/test_daily_mode_feishu_live.py`
- `pytest.ini` 新增 `feishu_live` marker

---

## 九、下一步计划

1. 修复 Moonshot 旧矩阵空事件库问题，让旧测试也能真实运行。
2. 修复 daemon stability 测试挂起问题。
3. 增加重启后记忆测试，目前预计失败，用于驱动 MemoryManager 持久化整改。
4. 增加主动预算跨日重置测试，目前预计失败，用于驱动 Continuity 整改。
5. 增加飞书线程回调测试，目前预计失败，用于驱动 FeishuAdapter 整改。
6. 增加 LLM-as-judge 行为评价器。
