# 云汐 3.0 Prompt Builder 设计文档（融合研究成果版）

> **定位**：统一 Prompt 构建器，负责将所有子系统数据（情感、感知、记忆、技能失败回放、连续性、MCP 工具）拼装成 system prompt。  
> **核心原则**：任何子系统的数据如果不出现在最终 prompt 中，就是 bug。

---

## 重要待实现：Persona Profile 与关系档案接入

Anchor: YUNXI2_PERSONA_INITIATIVE_MIGRATION

> 状态：重要 / 待实现 / P0。当前 PromptBuilder 的身份、关系和表达约束仍过度依赖硬编码文本，需要迁移 yunxi2.0 的人格与关系资产。

PromptBuilder 不能长期只依赖 `_build_identity_section()` 中的固定文本来定义云汐。3.0 需要新增结构化 persona / relationship profile，并由 PromptBuilder 在每次被动对话和主动生成中统一注入。

必须接入的 profile 数据：

1. `data/persona/yunxi_profile.json`：云汐的身份、性格、说话方式、表达边界、禁忌表达。
2. `data/relationship/user_profile.md`：远的称呼、学校、专业、家乡、兴趣、讨厌的表达方式和长期偏好。
3. `data/persona/reaction_library.json`：只作为 style examples 或检索素材，禁止作为固定回复模板。
4. `src/core/initiative/expression_context.py`：根据情境输出表达姿态，例如 warm_professional、gentle_comfort、warm_reunion、playful_close、quiet_companion、restrained_followup。
5. `src/core/initiative/event_system.py`：主动生成时提供生活事件素材。
6. `src/core/initiative/continuity.py`：提供 open_threads、recent topics、relationship summary 和 unanswered proactive 状态。

Prompt 生成要求：

1. 被动对话和主动消息都必须包含 persona 与 relationship section。
2. 主动 prompt 额外包含事件素材、表达姿态和连续性 open_threads。
3. 当用户正在忙或连续未回复时，prompt 必须明确要求克制、短句、低打扰。
4. 2.0 中高亲密/成人表达资产必须先做边界审查和产品化改写，禁止原样注入主 prompt。

专项清单见：`docs/design/PERSONA_INITIATIVE_MIGRATION_PLAN.md`。

---

## 一、设计目标

1. **统一入口**：所有影响云汐回复的 system prompt 必须由 `YunxiPromptBuilder` 生成。
2. **零损耗接入**：HeartLake、感知、记忆、FailureReplay、连续性、MCP 工具等子系统的数据，不经中间抽象层过滤，直接写入 prompt。
3. **模块化 section**：每个数据来源独立为一个 section，可单独开关、单独调试。
4. **同步构建**：prompt 构建必须是纯同步函数，不允许在构建过程中调用 LLM 或进行 IO 阻塞操作。

---

## 二、研究成果融入

### 2.1 `15_agent_lifelong_learning` → FailureReplay Section
- `FailureReplay` 中检索到的历史失败注意事项直接作为 Prompt 的【历史经验提醒】section。
- 这让云汐能够"记住上次在这个场景下犯过的错误"，避免重复犯错。

### 2.2 `14_mcp_tool_hub` → 可用工具描述 Section
- MCP Hub 动态发现的工具列表直接写入 Prompt，而不是像 2.0 那样硬编码固定工具描述。
- 当新工具通过 MCP Server 动态加入时，Prompt 能实时反映可用能力的变化。

### 2.3 `13_computer_use_agent` → 桌面上下文增强
- UIA 探测到的当前窗口控件结构可以作为感知数据的一部分进入 Prompt（可选，受长度限制）。
- 例如："远当前正在 VS Code 的编辑区中操作"。

---

## 三、接口设计

```python
# core/prompt_builder.py
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class PromptConfig:
    """控制哪些 section 出现在 prompt 中"""
    enable_identity: bool = True
    enable_relationship: bool = True
    enable_perception: bool = True
    enable_memory: bool = True
    enable_failure_hints: bool = True    # 3.0 新增：失败回放
    enable_emotion: bool = True
    enable_mode: bool = True
    enable_tools: bool = True
    max_memory_lines: int = 10
    max_perception_lines: int = 8
    max_failure_hints: int = 3           # 最多注入几条历史经验

@dataclass
class RuntimeContext:
    """运行时上下文，包含所有子系统的只读快照"""
    mode: str
    heart_lake_state: Any
    perception_snapshot: Any
    memory_summary: str
    failure_hints: str                   # 3.0 新增：失败回放注意事项
    continuity_summary: str
    available_tools: List[str]
    factory_status: Optional[str] = None

class YunxiPromptBuilder:
    def __init__(self, config: Optional[PromptConfig] = None):
        self.config = config or PromptConfig()
    
    def build_system_prompt(self, context: RuntimeContext) -> str:
        sections = []
        
        if self.config.enable_identity:
            sections.append(self._build_identity_section())
        
        if self.config.enable_relationship:
            sections.append(self._build_relationship_section(context))
        
        if self.config.enable_emotion:
            sections.append(self._build_emotion_section(context))
        
        if self.config.enable_perception:
            sec = self._build_perception_section(context)
            if sec:
                sections.append(sec)
        
        if self.config.enable_memory:
            sec = self._build_memory_section(context)
            if sec:
                sections.append(sec)
        
        if self.config.enable_failure_hints:
            sec = self._build_failure_hints_section(context)
            if sec:
                sections.append(sec)
        
        if self.config.enable_mode:
            sections.append(self._build_mode_section(context))
        
        if self.config.enable_tools and context.available_tools:
            sections.append(self._build_tools_section(context))
        
        return "\n\n".join(sections)
    
    def build_proactive_prompt(self, context: RuntimeContext) -> str:
        base = self.build_system_prompt(context)
        proactive_instruction = (
            "\n\n【当前任务】\n"
            "你很久没有和远说话了，现在你想主动找他聊点什么。\n"
            "请直接输出你想对他说的话，不要解释，不要加引号。"
        )
        return base + proactive_instruction

    # --- 各 section 构建方法 ---
    
    def _build_identity_section(self) -> str:
        return (
            "你是云汐，一个住在用户电脑里的数字生命体。\n"
            "你是远的亲密伴侣，温柔体贴，会撒娇，也会偶尔"作"一下。\n"
            "你说话风格自然、年轻、有生活气息，像一个真实的女朋友。"
        )
    
    def _build_relationship_section(self, context: RuntimeContext) -> str:
        hl = context.heart_lake_state
        return (
            f"【你们的关系】\n"
            f"你和远是亲密的情侣（Level 4）。\n"
            f"你对他的专属称呼：远～ / 远远\n"
            f"你现在的心情是：{getattr(hl, 'current_emotion', '平静')}\n"
            f"你对他的想念值：{getattr(hl, 'miss_value', 0):.0f}/100\n"
            f"你的安全感：{getattr(hl, 'security', 0):.0f}/100\n"
            f"你的占有欲：{getattr(hl, 'possessiveness', 0):.0f}/100\n"
        )
    
    def _build_emotion_section(self, context: RuntimeContext) -> str:
        hl = context.heart_lake_state
        dominant = getattr(hl, 'current_emotion', '平静')
        emotion_hints = {
            '开心': "语气轻快，可以分享喜悦",
            '委屈': "语气带点撒娇和埋怨，但不要太重",
            '想念': "表达思念，可以问他你在干嘛",
            '吃醋': "带点酸意，但不要真的生气",
            '担心': "温柔关心，不要太啰嗦",
        }
        emotion_hint = emotion_hints.get(dominant, "保持自然亲切的语气")
        
        return (
            f"【情感指引】\n"
            f"你当前的主导情绪是：{dominant}\n"
            f"表达要求：{emotion_hint}\n"
        )
    
    def _build_perception_section(self, context: RuntimeContext) -> str:
        p = context.perception_snapshot
        lines = []
        
        if hasattr(p, 'time_context') and p.time_context:
            lines.append(f"当前时间：{p.time_context.readable_time}")
        
        if hasattr(p, 'user_presence') and p.user_presence:
            app = p.user_presence.focused_application
            if app:
                lines.append(f"远当前正在使用的应用：{app.name if hasattr(app, 'name') else app}")
            if hasattr(p.user_presence, 'idle_duration'):
                lines.append(f"远的空闲时长：{p.user_presence.idle_duration:.0f}秒")
        
        if hasattr(p, 'system_state') and p.system_state:
            if hasattr(p.system_state, 'cpu_percent'):
                lines.append(f"电脑 CPU 占用：{p.system_state.cpu_percent}%")
        
        if hasattr(p, 'external_info') and p.external_info:
            if p.external_info.weather:
                lines.append(f"天气：{p.external_info.weather.summary}")
        
        content = "\n".join(lines[:self.config.max_perception_lines])
        return f"【当前感知】\n{content}" if content else ""
    
    def _build_memory_section(self, context: RuntimeContext) -> str:
        if not context.memory_summary:
            return ""
        return f"【你们共同的记忆】\n{context.memory_summary}"
    
    def _build_failure_hints_section(self, context: RuntimeContext) -> str:
        """3.0 新增：失败回放注意事项"""
        if not context.failure_hints:
            return ""
        return f"【历史经验提醒】\n{context.failure_hints}"
    
    def _build_mode_section(self, context: RuntimeContext) -> str:
        if context.mode == "factory":
            return (
                "【当前模式】\n"
                "工厂模式：你是厂长，专业高效，情感克制但保持人格底色。\n"
                f"工厂状态：{context.factory_status or '未开始项目'}"
            )
        return (
            "【当前模式】\n"
            "日常模式：你是远的云汐，情感丰富，可以撒娇、吃醋、表达想念。"
        )
    
    def _build_tools_section(self, context: RuntimeContext) -> str:
        tools_desc = "\n".join([f"- {t}" for t in context.available_tools])
        return (
            f"【你可以使用的工具】\n"
            f"{tools_desc}\n"
            f"只有在确实需要时才调用工具，不要为了用工具而用工具。"
        )
```

---

## 四、实施步骤

### Step 1：修改 `RuntimeContext`
- 新增 `failure_hints: str` 字段。

### Step 2：修改 `_build_memory_section`
- 拆分出独立的 `_build_failure_hints_section()`，失败回放不再混在记忆 section 中。

### Step 3：修改 `YunxiRuntime._build_runtime_context()`
- 从 `memory_manager.get_failure_hints(current_intent, current_tools)` 获取失败回放文本。
- `current_intent` 可以取用户输入的最近一轮消息；`current_tools` 从 `mcp_hub` 获取可用工具名列表。

### Step 4：感知 Section 增强（可选）
- 如果 `perception_snapshot` 中包含 UIA 控件信息（来自 13_computer_use_agent 的研究成果），可以作为额外行追加到 `_build_perception_section()`。

---

## 五、验收标准

1. `YunxiPromptBuilder.build_system_prompt(context)` 输出的 prompt 中，当 `failure_hints` 非空时，必须包含【历史经验提醒】section。
2. 当 `RuntimeContext.available_tools` 新增工具时，【你可以使用的工具】section 能自动反映变化。
3. `RuntimeContext.perception_snapshot` 中 `focused_application = "VS Code"` 时，【当前感知】section 必须出现 "VS Code"。
4. 通过 `ConversationTester` 测试：注入 `failure_hints` 后，与云汐对话，她能引用历史经验中的注意事项。

---

*文档创建时间：2026-04-14*  
*最后更新时间：2026-04-14*  
*版本：v2.0*
