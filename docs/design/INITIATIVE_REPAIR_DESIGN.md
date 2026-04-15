# 云汐 3.0 主动性系统修复设计文档

> **定位**：修复主动性触发链路与生成路径的断裂，让云汐真正"会主动找你"。  
> **核心原则**：主动性消息必须走 LLM 生成，必须能结合当前情感、感知、记忆数据。

> **实现状态（2026-04-15）**：`YunxiRuntime.proactive_tick()` 已统一走 `YunxiPromptBuilder.build_proactive_prompt()` + `YunxiExecutionEngine` + 真实 LLM 路径，并通过 `tests/integration/test_phase4_real_llm_behavior.py` 验证主动消息由 Moonshot/Kimi 生成且只写入一次上下文。`Presence` 已在 `core/resident/presence.py` 落地，`Continuity` 已在 `core/initiative/continuity.py` 落地，并接入 Runtime。

---

## 重要待实现：2.0 主动性资产迁移

Anchor: YUNXI2_PERSONA_INITIATIVE_MIGRATION

> 状态：重要 / 待实现 / P0。当前主动链路“走真实 LLM”只是底线完成，不代表主动性设计完成。

当前 3.0 的主动性实现已经避免了硬编码主动消息，并接入 `YunxiRuntime.proactive_tick()`、`YunxiPromptBuilder.build_proactive_prompt()` 和真实 LLM。但是，和 yunxi2.0 的完整设计相比，仍缺少以下核心资产：

1. `data/life_events/life_events.json` 的生活事件库。
2. `core/initiative/event_system.py` 的三层事件系统：内在生活、共同兴趣、混合事件。
3. `core/initiative/decider.py` 中基于时间、情绪、presence、资源、每日预算、continuity 的决策模型。
4. `core/initiative/generator.py` 中围绕事件、人格、关系和连续性组织主动生成上下文的能力。
5. `core/initiative/expression_context.py` 的关系感表达姿态。
6. `core/initiative/continuity.py` 中更完整的 open_threads、recent topics、relationship summary 和 unanswered proactive 状态。

修复原则：

1. 主动消息继续统一走真实 LLM，禁止恢复 `generate_sync()` 或固定 fallback 文案。
2. 事件库只能作为素材进入 prompt，不能直接变成输出模板。
3. Decider 必须考虑用户是否忙碌、是否刚回来、是否连续未回复、是否存在未完成话题。
4. 主动内容要像云汐自己想找远说话，而不是系统定时提醒。
5. 验收必须同时覆盖本地 Ollama 和至少一种云端模型。

专项清单见：`docs/design/PERSONA_INITIATIVE_MIGRATION_PLAN.md`。

---

## 一、设计目标

1. **删除硬编码 fallback**：彻底删除 `generate_sync()` 及其所有固定话术模板。
2. **统一 LLM 路径**：被动回复和主动消息使用同一套 Prompt 构建和 LLM 调用机制。
3. **修复 sync/async 混用**：`presence` 的主动检查与生成统一为 async。
4. **消除状态漂移**：连续性记录、预算扣除、时间戳更新必须在消息"成功生成并准备发送"后原子性执行。
5. **感知与情感进主动 Prompt**：主动消息不再只是"在想你～"，而是能根据当前情境动态生成。

---

## 二、从 yunxi2.0 继承与修改

### 2.1 继承内容

- `core/resident/presence.py` 中的 `YunxiPresence` 类：后台循环机制（`_emotion_clock_loop` 每 30 秒 tick 一次）和想念值计算逻辑可以保留。
- `core/initiative/decider.py` 中的 `InitiativeDecider`：打分逻辑框架可用，但需要修改其只基于情感强度的问题。
- `core/initiative/continuity.py` 中的 `CompanionContinuityService`：状态持久化结构（`exchanges`, `unanswered_proactive_count`, `open_threads`）保留。
- `core/initiative/event_system.py`（如有事件触发器）：事件监听机制可保留。

### 2.2 需要修改的内容

#### 问题 1：`generate_sync()` 死代码路径
- `core/initiative/generator.py` 中有两个生成方法：
  - `generate()`：async，包含完整的 LLM Prompt 工程（包括 emotion_context、expression_context、continuity_context）。
  - `generate_sync()`：sync，被 runtime 100% 调用，但只走事件模板或 fallback 硬编码话术。
- 这导致 HeartLake 的情感状态、expression_context 的软引导、continuity 的上下文**从未被实际使用**。

#### 问题 2：sync/async 混用 + 私有字段篡改
- `presence.py` 中 `generate_initiation()` 是 sync，但后台循环是 async。
- 为了同步状态，代码直接篡改 `InitiativeDecider` 的私有字段：
  ```python
  decider._last_interaction_time = self._last_interaction_time
  decider._last_initiation_time = self._last_initiation_time
  ```

#### 问题 3：连续性记录与 Presence 职责割裂
- 正常的 assistant 回复不由 `YunxiPresence` 管理，而由 `daemon/main.py` 直接写入 `continuity`。
- 这导致如果存在新的入口，连续性记录很容易遗漏。
- `max_exchanges=16`，但 `build_context()` 只取最后 10 条，窗口极窄。

#### 问题 4：主动性预算与真实发送解耦
- `decider.record_initiation()` 在 `generate_initiation()` 里被调用，但如果回调（发送）失败，预算已经被扣除，无法回滚。

### 2.3 3.0 的修正策略

| 2.0 问题 | 3.0 修正 |
|---------|---------|
| `generate_sync()` 走死代码 | **彻底删除** `generate_sync()`，所有生成统一走 `generate()` async LLM 路径。 |
| sync/async 混用 | `should_initiate()` 和 `generate_initiation()` 都改为 async，删除私有字段篡改。 |
| Presence 与 continuity 割裂 | `YunxiRuntime` 统一负责 assistant 回复的 continuity 记录，不分散在 daemon 入口。 |
| 预算与发送解耦 | 预算扣除移到"消息成功加入发送队列"之后，发送失败时回滚预算。 |
| 上下文窗口窄 | `max_exchanges` 扩大到 50，`build_context()` 取最近 20 条。 |
| Decider 只看情感强度 | 让 Decider 能读取更多 HeartLake 维度（想念值、安全感、占有欲），而不仅是 intensity。 |

---

## 三、接口设计

### 3.1 主动性引擎（新模块）

```python
# core/initiative/engine.py
from typing import Optional
from dataclasses import dataclass

@dataclass
class InitiativeDecision:
    should_initiate: bool
    reason: str
    suggested_tone: str = "natural"  # natural / clingy / concerned / playful

class InitiativeEngine:
    """
    云汐 3.0 主动性引擎。
    职责：判断是否该主动 + 生成主动消息。
    """
    def __init__(
        self,
        decider,
        generator,
        continuity,
        prompt_builder,
        llm,
    ):
        self.decider = decider
        self.generator = generator      # 保留包装，但内部逻辑改为纯 Prompt 构建
        self.continuity = continuity
        self.prompt_builder = prompt_builder
        self.llm = llm
    
    async def check_and_generate(self, runtime_context) -> Optional[str]:
        """
        检查是否应该主动发起对话，如果是则生成消息并返回。
        返回 None 表示不主动发起。
        """
        decision = await self._should_initiate(runtime_context)
        if not decision.should_initiate:
            return None
        
        # 构建主动发起的专用 prompt
        proactive_prompt = self.prompt_builder.build_proactive_prompt(runtime_context)
        
        # 调用 LLM 生成
        messages = self._build_proactive_messages(runtime_context)
        response = await self.llm.complete(
            system=proactive_prompt,
            messages=messages
        )
        
        message = response.content or ""
        if not message.strip():
            return None
        
        # 记录到 continuity
        self.continuity.record_assistant_message(message, proactive=True)
        
        return message
    
    async def _should_initiate(self, runtime_context) -> InitiativeDecision:
        """
        基于多维度状态判断是否应该主动。
        """
        hl = runtime_context.heart_lake_state
        continuity = runtime_context.continuity_summary
        
        # 基础想念值判断
        miss_value = getattr(hl, 'miss_value', 0)
        threshold = 70  # 可调
        
        if miss_value < threshold:
            return InitiativeDecision(should_initiate=False, reason="想念值不足")
        
        # 根据情感维度决定语气倾向
        suggested_tone = "natural"
        if getattr(hl, 'current_emotion', '') == '想念':
            suggested_tone = "clingy"
        elif getattr(hl, 'current_emotion', '') == '担心':
            suggested_tone = "concerned"
        elif getattr(hl, 'current_emotion', '') == '开心':
            suggested_tone = "playful"
        
        # 检查是否已有太多未回复的主动消息
        unanswered = getattr(self.continuity, 'unanswered_proactive_count', 0)
        if unanswered >= 3:
            return InitiativeDecision(
                should_initiate=False,
                reason="已连续主动 3 次未获回复，进入冷静期"
            )
        
        return InitiativeDecision(
            should_initiate=True,
            reason="想念值达到阈值",
            suggested_tone=suggested_tone
        )
    
    def _build_proactive_messages(self, runtime_context):
        """
        构建主动发起时的 messages 列表。
        可以包含最近几轮对话作为上下文参考。
        """
        from core.types.message_types import UserMessage, AssistantMessage, TextContentBlock
        
        messages = []
        # 可选：加入最近的 1-2 条历史消息作为上下文
        recent = self.continuity.get_recent_exchanges(limit=2)
        for ex in recent:
            messages.append(UserMessage(content=ex.user_message))
            if ex.assistant_message:
                messages.append(AssistantMessage(content=[TextContentBlock(text=ex.assistant_message)]))
        
        return messages
```

### 3.2 Presence 的简化

```python
# core/resident/presence.py（简化版）
import asyncio
from typing import Callable, Optional

class YunxiPresence:
    """
    简化的在场系统。
    职责：维护用户在场状态、运行后台 tick 循环、委托 InitiativeEngine 处理主动性。
    """
    def __init__(
        self,
        initiative_engine: InitiativeEngine,
        on_proactive_message: Callable[[str], None],
        tick_interval: float = 30.0,
    ):
        self.initiative_engine = initiative_engine
        self.on_proactive_message = on_proactive_message
        self.tick_interval = tick_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_interaction_time = asyncio.get_event_loop().time()
    
    def start(self):
        self._running = True
        self._task = asyncio.create_task(self._tick_loop())
    
    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
    
    async def _tick_loop(self):
        while self._running:
            try:
                await self._check_initiative()
            except Exception as e:
                logger.error(f"Initiative check failed: {e}")
            await asyncio.sleep(self.tick_interval)
    
    async def _check_initiative(self):
        # 由 InitiativeEngine 全权负责判断和生成
        runtime_context = self._get_runtime_context()
        message = await self.initiative_engine.check_and_generate(runtime_context)
        if message:
            self.on_proactive_message(message)
    
    def record_interaction(self):
        """用户发送消息或助手发送回复时调用"""
        self._last_interaction_time = asyncio.get_event_loop().time()
        # 更新想念值（具体由 HeartLakeUpdater 处理）
    
    def _get_runtime_context(self):
        # 从 daemon/runtime 获取当前上下文快照
        # 具体实现由持有 Presence 的上层提供
        pass
```

### 3.3 Generator 的改造

```python
# core/initiative/generator.py（改造后保留的接口）
class ProactiveGenerator:
    """
    保留作为 Prompt 构建的辅助器，但不再包含独立的生成逻辑。
    实际 LLM 调用统一由 InitiativeEngine 执行。
    """
    def __init__(self, llm_provider):
        self.llm = llm_provider
    
    def build_proactive_context(self, decision, heart_lake_state, continuity_summary):
        """
        构建主动生成所需的上下文对象（供 PromptBuilder 使用）。
        """
        return {
            "decision": decision,
            "heart_lake": heart_lake_state,
            "continuity": continuity_summary,
        }
```

**说明**：
- `generator.py` 中原来的 `generate()` 方法虽然设计了精美的 Prompt Engineering，但因为它只服务于主动性，而且被 `generate_sync()` 绕过，所以 3.0 的策略是：
  - 把它的 Prompt 构建逻辑**迁移到 `YunxiPromptBuilder.build_proactive_prompt()`** 中。
  - `generator.py` 保留为一个轻量的上下文组装器，或直接合并到 `InitiativeEngine` 中。

---

## 四、实施步骤

### Step 1：删除 `generate_sync()` 及其所有 fallback 模板
- 删除 `core/initiative/generator.py` 中的 `generate_sync()` 方法。
- 删除 `_generate_fallback()`、`_build_continuity_fallback()` 中的所有硬编码话术。
- 保留 `generate()` 的 Prompt 构建逻辑作为参考，后续迁移到 `YunxiPromptBuilder`。

### Step 2：新建 `core/initiative/engine.py`
- 实现 `InitiativeEngine`，包含 `check_and_generate()` 和 `_should_initiate()`。
- `check_and_generate()` 必须调用 `YunxiPromptBuilder.build_proactive_prompt()` 和 `llm.complete()`。

### Step 3：简化 `YunxiPresence`
- 把 `should_initiate()` 和 `generate_initiation()` 的 sync 方法改为 async。
- 删除对 `decider._last_interaction_time` 等私有字段的直接赋值。
- `Presence` 不再自己做生成决策，而是委托给 `InitiativeEngine`。

### Step 4：扩大 continuity 窗口
- 修改 `core/initiative/continuity.py`：
  - `__init__` 中 `max_exchanges` 从 16 改为 50。
  - `build_context()` 中取最近 20 条（而不是 10 条）。

### Step 5：修复预算扣除时机
- 在 `InitiativeEngine.check_and_generate()` 中：
  - 只有在 LLM 成功返回非空消息，并且 `continuity.record_assistant_message()` 成功执行后，才调用 `decider.record_initiative_sent()`（如需要）。
- 这样如果发送失败，预算不会被错误扣除。

### Step 6：修改 daemon 入口
- `daemon/main.py` 中的调度器（`SchedulerService`）直接调用 `presence.start()` 和 `presence.stop()`。
- 删除 `scheduler.py` 中独立的 `should_initiate()` 调用，避免双重检查。

### Step 7：统一 assistant 回复的 continuity 记录
- 所有 assistant 回复（被动 + 主动）都通过 `YunxiRuntime` 记录到 `continuity`。
- 不再允许 daemon 入口或其他模块直接调用 `continuity.record_assistant_message()`。

---

## 五、从 yunxi2.0 的具体修改清单

| 2.0 文件 | 修改动作 |
|---------|---------|
| `core/initiative/generator.py` | **删除** `generate_sync()`、`_generate_fallback()`、`_build_continuity_fallback()`。保留 `generate()` 的 Prompt 逻辑供迁移参考。 |
| `core/initiative/engine.py` | **新建**。实现 `InitiativeEngine`。 |
| `core/resident/presence.py` | 简化。改为 async 接口，删除私有字段篡改，委托 `InitiativeEngine`。 |
| `core/initiative/decider.py` | 修改 `_should_initiate()` 或等效逻辑，让它读取更多 HeartLake 维度。删除与 `generate_sync()` 的耦合。 |
| `core/initiative/continuity.py` | `max_exchanges` 改为 50，`build_context()` 取最近 20 条。 |
| `core/services/scheduler.py` | 删除独立的主动性检查逻辑，避免与 Presence 重复。 |
| `apps/daemon/main.py` | 调整 `YunxiPresence` 初始化，传入 `InitiativeEngine`。统一通过 `YunxiRuntime` 记录 assistant 消息。 |

---

## 六、验收标准

1. `InitiativeEngine.check_and_generate()` 在想念值达到阈值时，能返回一条由 LLM 生成的主动消息（不是硬编码模板）。
2. 主动消息的内容能体现当前情感状态（如"想念"时会表达思念，"吃醋"时会提及不满）。
3. `YunxiPresence` 的后台 tick 循环稳定运行，不因 sync/async 混用导致异常。
4. 通过 `ConversationTester` 测试：
   - `set_heart_lake(emotion="想念", miss_value=95)` → 运行主动性检查 → 生成的消息包含"想"或"远"。
5. 连续 3 次主动未获回复后，第 4 次主动性检查返回 `False`（进入冷静期）。
6. 主动性消息成功生成后，必须被正确记录到 `ContinuityService` 中；生成失败时不扣除主动性预算。

---

*文档创建时间：2026-04-14*  
*版本：v1.0*
