"""记忆管理器（融合终身学习完整版）。

提供记忆存储、经验记录、技能匹配、失败回放等接口，
并集成 ExperienceBuffer / PatternMiner / SkillDistiller / SkillLibrary / FailureReplay / ParamFiller。
"""

import os
from typing import Any, Dict, List, Optional

from domains.memory.skills.experience_buffer import ExperienceBuffer
from domains.memory.skills.failure_replay import FailureReplay
from domains.memory.skills.param_filler import ParamFiller
from domains.memory.skills.pattern_miner import PatternMiner
from domains.memory.skills.skill_distiller import SkillDistiller
from domains.memory.skills.skill_library import SkillLibrary


class MemoryManager:
    """记忆管理器。"""

    def __init__(
        self,
        base_path: str = "data/memory",
        embedding_provider: Optional[str] = None,
    ) -> None:
        self.base_path = base_path
        self._preferences: List[str] = []
        self._episodes: List[str] = []
        self._promises: List[str] = []

        # 终身学习子系统
        self.experience_buffer = ExperienceBuffer(
            db_path=os.path.join(base_path, "skills", "experience.db")
        )
        self.pattern_miner = PatternMiner(embedding_provider=embedding_provider)
        self.skill_distiller = SkillDistiller()
        self.skill_library = SkillLibrary(
            db_path=os.path.join(base_path, "skills", "skill_library.db"),
            embedding_provider=embedding_provider,
        )
        self.failure_replay = FailureReplay(
            db_path=os.path.join(base_path, "skills", "failures.db")
        )
        self.param_filler = ParamFiller()

    async def initialize(self) -> None:
        """异步初始化所有涉及模型加载的子系统。"""
        await self.pattern_miner.initialize()
        await self.skill_library.initialize()

    def record_preference(self, content: str) -> None:
        """记录用户偏好。"""
        self._preferences.append(content)

    def record_episode(self, content: str) -> None:
        """记录事件片段。"""
        self._episodes.append(content)

    def record_promise(self, content: str) -> None:
        """记录承诺。"""
        self._promises.append(content)

    def add_raw_memory(self, category: str, content: str) -> None:
        """按分类写入原始记忆。"""
        if category == "preference":
            self._preferences.append(content)
        elif category == "episode":
            self._episodes.append(content)
        elif category == "promise":
            self._promises.append(content)

    def get_memory_summary(self, limit: int = 10) -> str:
        """获取记忆摘要文本。"""
        lines: List[str] = []
        if self._preferences:
            lines.append("远的偏好：" + "；".join(self._preferences[-limit:]))
        if self._episodes:
            lines.append("共同经历：" + "；".join(self._episodes[-limit:]))
        if self._promises:
            lines.append("承诺：" + "；".join(self._promises[-limit:]))
        return "\n".join(lines)

    def record_experience(
        self,
        intent_text: str,
        actions: List[Dict[str, Any]],
        outcome: str,
        source: str,
        failure_reason: str = "",
    ) -> None:
        """记录一次经验到经验池，并在失败时同步记录失败回放。"""
        self.experience_buffer.add(
            intent_text=intent_text,
            actions=actions,
            outcome=outcome,
            source=source,
            failure_reason=failure_reason,
        )

        if outcome == "failure" and failure_reason:
            tool_name = ""
            if actions and isinstance(actions[0], dict):
                tool_name = actions[0].get("tool", "")
            self.failure_replay.record(
                intent_summary=intent_text,
                tool_name=tool_name,
                failure_reason=failure_reason,
                context_keywords=[tool_name] + intent_text.lower().split()[:5],
            )

    def record_skill_outcome(self, skill_name: str, success: bool) -> None:
        """记录技能执行结果。"""
        self.skill_library.record_outcome(skill_name, success)

    async def try_skill(self, user_input: str) -> Optional[Dict[str, Any]]:
        """尝试匹配已知技能。"""
        matches = await self.skill_library.retrieve(
            user_input, top_k=1, threshold=0.60
        )
        if not matches:
            return None

        skill = matches[0]
        params = self.param_filler.fill(user_input, skill)

        missing = [p for p in skill["parameters"] if p not in params or not params[p]]
        if missing:
            return None

        actions = []
        for action in skill["actions"]:
            filled_args = {}
            for k, v in action.get("args", {}).items():
                if isinstance(v, str):
                    filled_args[k] = v.format(**params)
                else:
                    filled_args[k] = v
            actions.append({"tool": action["tool"], "args": filled_args})

        return {
            "skill_name": skill["skill_name"],
            "actions": actions,
            "parameters": params,
        }

    def get_failure_hints(
        self, intent: str = "", tools: Optional[List[str]] = None
    ) -> str:
        """获取失败回放提示文本。"""
        hints = self.failure_replay.retrieve(intent, tools, limit=3)
        if not hints:
            return ""
        return "\n".join([f"- 注意：{h}" for h in hints])

    def add_failure_hint(self, hint: str) -> None:
        """手动注入失败提示（测试用）。"""
        self.failure_replay.record(
            intent_summary="manual_test",
            tool_name="",
            failure_reason=hint,
            suggestion=hint,
            context_keywords=hint.lower().split(),
        )

    async def run_skill_learning_cycle(self) -> None:
        """后台学习周期：从经验池中挖掘模式并蒸馏为技能。"""
        experiences = self.experience_buffer.get_recent(limit=500, source="mcp_audit")
        if len(experiences) < 3:
            return

        patterns = await self.pattern_miner.mine(experiences, min_cluster_size=3)

        for pattern in patterns:
            if pattern["confidence"] < 0.5:
                continue

            skill = self.skill_distiller.distill(pattern)

            existing = await self.skill_library.retrieve(
                skill["skill_name"], top_k=1, threshold=0.99
            )
            if existing and existing[0]["skill_name"] == skill["skill_name"]:
                skill["version"] = existing[0].get("version", 1) + 1

            self.skill_library.add_skill(skill)
