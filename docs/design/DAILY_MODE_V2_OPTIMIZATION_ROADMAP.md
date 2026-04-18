# 云汐日常模式 v2 后续优化路线图

> **目标**：从"可用"打磨到"几乎完美"。  
> **状态**：截至 2026-04-17，P0/P1/P2 已完成，233 测试全绿，SemanticAppraiser 已接入生产流程。

---

## 一、本轮已完成（ recap ）

| 能力 | 状态 | 关键验证 |
|:---|:---|:---|
| Narrative Prompt | ✅ 默认启用 | 真实 LLM 对比：女友感更强、幻觉更低 |
| 感知→情感链路 | ✅ | activity_state 驱动想念/安全感/俏皮感 |
| SemanticAppraiser | ✅ 接入生产 | Hybrid 智能触发，支持 Ollama + 云端 |
| Persona Profile | ✅ 已接入 | yunxi_profile.json + user_profile.md 注入 prompt |
| 情绪动力学 | ✅ | 惯性(0.7) + 持续性(30s) + 冷却(90s) |
| Presence Murmur | ✅ | 2h 浸泡通过，正向锚点校验 |
| 工具自然闭环 | ✅ | 执行结果由 LLM 做最终表达 |

---

## 二、高优先级：影响体验的关键缺口

### 2.1 HeartLake 恢复逻辑与语义情绪冲突 ❗

**问题**：`update_from_perception()` **总是先调用** `apply_natural_recovery()`，然后再做感知评估。这意味着：
- 语义评估器刚把情绪设为"委屈"，下一次感知 tick（每 60s）就把情绪拖回"平静"
- `valence`/`arousal` 被恢复持续拖向 0，语义评估设定的非零值无法保持

**修复方案**：
```python
# 方案 A：感知 tick 中，如果最近有语义评估（< 120s），跳过 recovery
if now - self._last_semantic_appraisal_at < 120:
    skip_recovery = True

# 方案 B：recovery 只应用在无活跃情绪的维度上
# 如果 current_emotion 不是"平静"，只恢复 valence/arousal，不恢复其他维度
```

**验收**：语义评估的情绪能持续至少 2 分钟，不被感知 tick 抹掉。

### 2.2 InitiativeEngine 未读取 compound_labels 和 appraisal_reason ❗

**问题**：`SemanticAppraiser` 返回的 `compound_labels`（如"刚从平静转来"、"还有一点委屈"）和 `reason`（如"远说了反话"）只进入了 prompt，**没有被 initiative engine 使用**。 initiative 的评分只读 `current_emotion` 字符串。

**影响**：云汐的情绪层次（"委屈但假装没事"）不影响主动陪伴策略。她不会因为"还有一点委屈"而减少主动，也不会因为"刚从平静转来"而更加谨慎。

**修复方案**：
- `InitiativeEngine._score_decision()` 读取 `compound_labels`
- 含"委屈"/"脆弱"标签时降低打扰意愿（-0.2）
- 含"刚从"过渡标签时增加克制（+0.15 打扰成本）
- `last_appraisal_reason` 进入 initiative prompt，让云汐知道"为什么现在不太想打扰"

### 2.3 情绪标签在感知 tick 中被静默覆盖 ❗

**问题**：`update_from_perception()` 的 `elif` 链没有 final `else`。如果用户在 work+fullscreen+低输入 状态（`input_rate < 10`），代码 fall through 到 `idle < 60` 分支，**错误地增加想念值**。

**修复**：补充 `else` 分支，明确处理未匹配的感知状态，不修改情绪或只微调。

---

## 三、中优先级：质量提升

### 3.1 Narrative 模式补全：memory / failure_hints / continuity 的叙事化

**问题**：Narrative 模式下 emotion/perception/relationship 已叙事化，但 memory、failure_hints、continuity 仍是 raw data 风格（"远的称呼：远"、"- 远的事实：..."）。

**修复**：为这些 section 添加叙事化包装：
- Memory → "你还记得..." / "上次远提到..."
- Failure hints → "上次在这个场景下，你曾犯过..."
- Continuity → "远还没回复你上次的..."

### 3.2 InnerVoice section 的可选化与质量验证

**问题**：InnerVoice 强制开启，没有 `enable_inner_voice` 开关。内容重复了 MoodNarrative 和 PerceptionNarrative 的信息。

**修复**：
1. PromptConfig 添加 `enable_inner_voice: bool = True`
2. 验证 InnerVoice 是否真正提升 LLM 输出质量（A/B 测试）
3. 如果效果不显著，默认关闭以节省 token

### 3.3 硬编码阈值配置化

**问题**：大量阈值写死在代码中，难以根据真实使用调优：

| 位置 | 硬编码值 | 建议 |
|:---|:---|:---|
| HeartLake | `emotion_inertia = 0.7` | 从环境变量读取 |
| HeartLake | `emotion_persistence_seconds = 30.0` | 从环境变量读取 |
| InitiativeEngine | `TRIGGER_THRESHOLD = 0.55` | 配置文件 |
| InitiativeEngine | `cooldown_seconds = 300.0` | 配置文件 |
| InitiativeEngine | 情绪加分（担心+0.45 等） | 配置文件 |
| Runtime | presence murmur 长度上限 80 | 配置文件 |

**修复**：创建 `config/daily_mode.yaml`，集中管理日常模式参数。

### 3.4 `relationship_level` 从静态变为动态

**问题**：`relationship_level` 硬编码为 4（伴侣期），从不变化。yunxi2.0 设计的 L1→L2→L3→L4 升级仪式完全未实现。

**修复**：
1. 记录互动次数、深度对话次数、承诺完成数
2. 达到阈值时触发升级对话（需要专门的 prompt 和对话流程）
3. relationship_level 影响：称呼库、主动频率阈值、表达边界

---

## 四、低优先级 / 探索方向

### 4.1 `valence`/`arousal` 的宿命

**问题**：这两个 PAD 维度被更新但从不被内部逻辑读取。它们是"死维度"。

**选项**：
- A. 移除它们（简化模型）
- B. 让它们驱动 initiative：高 arousal → 更活跃的主动；低 valence → 更克制的表达
- C. 映射到现有维度：valence → security 代理；arousal → playfulness 代理

**建议**：选 B，让 PAD 真正参与行为决策。

### 4.2 多轮对话情绪持续性

**问题**：当前情绪评估是**单轮独立**的。用户说"你真好，都不理我了"→委屈；用户接着说"开玩笑的啦"→开心。但云汐的回复应该体现**情绪的残留**——"哼...（委屈）... 好吧，知道你是开玩笑的（逐渐恢复）"。

**探索**：在 `continuity` 中记录最近的情绪轨迹，prompt 中注入"你上一轮感到...现在逐渐..."，让 LLM 生成情绪过渡式回复。

### 4.3 长期情绪日记

**问题**：云汐没有"今天整体心情如何"的概念。每天的语义评估结果散落在各个消息中，没有聚合。

**探索**：每日结束时生成 `emotional_summary`，记录：
- 今天主导情绪是什么
- 什么时候最开心 / 最委屈
- 远的情绪模式（他今天压力大吗）
- 第二天初始状态受此 summary 影响

### 4.4 云端模型成本优化

**问题**：如果每条复杂消息都调云端 SemanticAppraiser，一天 50 条 × ¥0.003 = ¥0.15，不贵但积少成多。

**优化**：
- 本地缓存：相同文本的评估结果缓存 1 小时
- 批量评估：把多条消息聚合成一次 LLM 调用
- 降级策略：云端失败时自动切 Ollama，Ollama 失败时纯规则

---

## 五、模型与基础设施

### 5.1 模型选择矩阵

| 场景 | 推荐模型 | 延迟 | 备注 |
|:---|:---|:---|:---|
| 语义评估 | Moonshot-v1-8k | 1-3s | 云端，快且稳定 |
| 语义评估（离线） | gpt-oss:20b | 17s | 本地，隐私好 |
| 语义评估（备用） | qwen3-vl:8b | 45-60s | 本地，不建议同步 |
| 主对话 | Moonshot/Claude/GPT-4 | 2-10s | 按现有配置 |
| Presence Murmur | qwen3:4b | 5-15s | 轻量任务，本地即可 |

### 5.2 真实使用验证清单

在继续打磨代码前，建议先做一轮**真实使用验证**：

1. **连续对话测试**：和云汐聊 20 轮，观察情绪标签是否正确过渡
2. **讽刺识别测试**：故意说反话，观察她是否从"开心"转为"委屈"
3. **工作状态测试**：全屏工作 30 分钟，观察她是否克制主动
4. **记忆召回测试**：提到之前的承诺或共同记忆，观察她是否记得
5. **情绪日记检查**：一天结束后查看 emotional_summary 是否合理

---

## 六、下一步推荐动作

**如果你希望继续代码打磨**：

1. **修复 2.1**（恢复逻辑冲突）→ 1-2 小时
2. **修复 2.2**（compound_labels 进 initiative）→ 2-3 小时
3. **实现 3.1**（memory/failure 叙事化）→ 2-3 小时
4. **实现 3.3**（阈值配置化）→ 2-3 小时

**如果你希望先验证真实体验**：

1. 配置 `YUNXI_EMOTION_BACKEND=cloud` 启动日常模式
2. 做上述 5 项真实使用验证
3. 收集情绪标签日志，检查是否符合预期
4. 根据体验反馈决定下一步优化方向

**核心判断**：当前代码已经"可用且有一定女友感"，但距离"几乎完美"还需要解决 **恢复逻辑冲突** 和 **情绪标签进 initiative** 这两个结构性问题。修复后，云汐的情绪状态才能真正持续存在并驱动行为，而不仅仅是 prompt 中的一段文字。
