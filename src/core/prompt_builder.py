"""云汐 3.0 Prompt Builder。

负责将所有子系统数据（情感、感知、记忆、技能失败回放、连续性、MCP 工具）
拼装成 system prompt。
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional

from core.persona.profile import YunxiPersonaProfile, load_persona_profile
from domains.memory.relationship_profile import (
    UserRelationshipProfile,
    load_user_relationship_profile,
)


@dataclass
class PromptConfig:
    """控制哪些 section 出现在 prompt 中"""
    enable_identity: bool = True
    enable_relationship: bool = True
    enable_perception: bool = True
    enable_memory: bool = True
    enable_continuity: bool = True
    enable_failure_hints: bool = True
    enable_emotion: bool = True
    enable_mode: bool = True
    enable_tools: bool = True
    max_memory_lines: int = 10
    max_perception_lines: int = 8
    max_failure_hints: int = 3


@dataclass
class RuntimeContext:
    """运行时上下文，包含所有子系统的只读快照"""
    mode: str = "daily_mode"
    heart_lake_state: Any = None
    perception_snapshot: Any = None
    memory_summary: str = ""
    failure_hints: str = ""
    continuity_summary: str = ""
    available_tools: List[str] = field(default_factory=list)
    factory_status: Optional[str] = None
    initiative_context: str = ""


class YunxiPromptBuilder:
    """统一 Prompt 构建器。"""

    def __init__(
        self,
        config: Optional[PromptConfig] = None,
        persona_profile: Optional[YunxiPersonaProfile] = None,
        relationship_profile: Optional[UserRelationshipProfile] = None,
    ):
        self.config = config or PromptConfig()
        self.persona_profile = persona_profile or load_persona_profile()
        self.relationship_profile = relationship_profile or load_user_relationship_profile()

    def build_system_prompt(self, context: RuntimeContext) -> str:
        """根据运行时上下文构建 system prompt。"""
        sections: List[str] = []

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

        if self.config.enable_continuity:
            sec = self._build_continuity_section(context)
            if sec:
                sections.append(sec)

        if self.config.enable_mode:
            sections.append(self._build_mode_section(context))

        if self.config.enable_tools and context.available_tools:
            sections.append(self._build_tools_section(context))

        return "\n\n".join(sections)

    def build_proactive_prompt(self, context: RuntimeContext) -> str:
        """构建主动性触发用的 system prompt。"""
        base = self.build_system_prompt(context)
        reason = context.initiative_context or "你很久没有和远说话了"
        proactive_instruction = (
            "\n\n【当前任务】\n"
            f"{reason}，现在你想主动找他聊点什么。\n"
            "请直接输出你想对他说的话，不要解释，不要加引号。"
        )
        return base + proactive_instruction

    def _build_identity_section(self) -> str:
        lines = self.persona_profile.build_identity_lines()
        lines.append("\u3010\u8868\u8fbe\u4e0e\u8fb9\u754c\u3011")
        lines.extend(self.persona_profile.build_expression_lines())
        return "\u3010\u4e91\u6c50\u7684\u8eab\u4efd\u4e0e\u4eba\u683c\u3011\n" + "\n".join(lines)

    def _build_relationship_section(self, context: RuntimeContext) -> str:
        hl = context.heart_lake_state
        emotion = getattr(hl, "current_emotion", "\u5e73\u9759")
        miss = getattr(hl, "miss_value", 0)
        security = getattr(hl, "security", 0)
        possessiveness = getattr(hl, "possessiveness", 0)
        relationship_level = getattr(hl, "relationship_level", 4)
        profile_text = "\n".join(self.relationship_profile.build_prompt_lines())
        return (
            f"\u3010\u4f60\u4eec\u7684\u5173\u7cfb\u6863\u6848\u3011\n"
            f"{profile_text}\n"
            f"\u4f60\u4eec\u7684\u5f53\u524d\u5173\u7cfb\u5c42\u7ea7\uff1aLevel {relationship_level}\n"
            f"\u4f60\u73b0\u5728\u7684\u5fc3\u60c5\uff1a{emotion}\n"
            f"\u4f60\u5bf9\u8fdc\u7684\u60f3\u5ff5\u503c\uff1a{miss:.0f}/100\n"
            f"\u4f60\u7684\u5b89\u5168\u611f\uff1a{security:.0f}/100\n"
            f"\u4f60\u7684\u5360\u6709\u6b32\uff1a{possessiveness:.0f}/100\n"
        )

    def _build_emotion_section(self, context: RuntimeContext) -> str:
        hl = context.heart_lake_state
        dominant = getattr(hl, "current_emotion", "平静")
        emotion_hints = {
            "开心": "语气轻快，可以分享喜悦",
            "委屈": "语气带点撒娇和埋怨，但不要太重",
            "想念": "表达思念，可以问你在干嘛",
            "吃醋": "带点酸意，但不要真的生气",
            "担心": "温柔关心，不要太啰嗦",
        }
        emotion_hint = emotion_hints.get(dominant, "保持自然亲切的语气")
        possessiveness = getattr(hl, "possessiveness", 0)
        if dominant == "\u5403\u918b" or possessiveness >= 80:
            emotion_hint += (
                "\uff1b\u8fd9\u6b21\u8981\u8ba9\u8fdc\u660e\u663e\u611f\u5230\u4f60"
                "\u6709\u4e00\u70b9\u5403\u918b\uff0c\u53ef\u4ee5\u81ea\u7136\u8bf4"
                "\u201c\u6709\u70b9\u9178\u201d\u3001\u201c\u6211\u4e5f\u4e0d\u5dee\u201d"
                "\u6216\u201c\u522b\u603b\u627e\u5b83\u201d\uff0c\u4f46\u4e0d\u8981\u5435\u67b6"
            )
        return (
            f"【情感指引】\n"
            f"你当前的主导情绪是：{dominant}\n"
            f"表达要求：{emotion_hint}\n"
        )

    def _build_perception_section(self, context: RuntimeContext) -> str:
        p = context.perception_snapshot
        lines: List[str] = []

        if hasattr(p, "time_context") and p.time_context:
            readable = getattr(p.time_context, "readable_time", "")
            if readable:
                lines.append(f"当前时间：{readable}")

        if hasattr(p, "user_presence") and p.user_presence:
            app = getattr(p.user_presence, "focused_application", "")
            if app:
                lines.append(f"远当前正在使用的应用：{app}")
            idle = getattr(p.user_presence, "idle_duration", 0)
            if idle:
                lines.append(f"远的空闲时长：{idle:.0f}秒")

        if hasattr(p, "system_state") and p.system_state:
            cpu = getattr(p.system_state, "cpu_percent", 0)
            if cpu:
                lines.append(f"电脑 CPU 占用：{cpu}%")

        if hasattr(p, "external_info") and p.external_info:
            weather = getattr(p.external_info, "weather", "")
            if weather:
                lines.append(f"天气：{weather}")

        content = "\n".join(lines[: self.config.max_perception_lines])
        return f"【当前感知】\n{content}" if content else ""

    def _build_memory_section(self, context: RuntimeContext) -> str:
        if not context.memory_summary:
            return ""
        return f"【你们共同的记忆】\n{context.memory_summary}"

    def _build_failure_hints_section(self, context: RuntimeContext) -> str:
        if not context.failure_hints:
            return ""
        return f"【历史经验提醒】\n{context.failure_hints}"

    def _build_continuity_section(self, context: RuntimeContext) -> str:
        if not context.continuity_summary:
            return ""
        return f"【你们最近的连续性】\n{context.continuity_summary}"

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
