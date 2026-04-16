"""记忆管理器（融合终身学习完整版）。

提供记忆存储、经验记录、技能匹配、失败回放等接口，
并集成 ExperienceBuffer / PatternMiner / SkillDistiller / SkillLibrary / FailureReplay / ParamFiller。
"""

import json
import os
from pathlib import Path
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
        self._relationship_memory_path = Path(base_path) / "relationship_memory.json"
        self._preferences: List[str] = []
        self._episodes: List[str] = []
        self._promises: List[str] = []
        self._load_relationship_memory()

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

    async def close(self) -> None:
        """释放记忆子系统持有的外部资源。"""
        await self.pattern_miner.close()
        await self.skill_library.close()

    def record_preference(self, content: str) -> None:
        """记录用户偏好。"""
        self._add_unique(self._preferences, content)
        self._save_relationship_memory()

    def record_episode(self, content: str) -> None:
        """记录事件片段。"""
        self._add_unique(self._episodes, content)
        self._save_relationship_memory()

    def record_promise(self, content: str) -> None:
        """记录承诺。"""
        self._add_unique(self._promises, content)
        self._save_relationship_memory()

    def add_raw_memory(self, category: str, content: str) -> None:
        """按分类写入原始记忆。"""
        if category == "preference":
            self._add_unique(self._preferences, content)
        elif category == "episode":
            self._add_unique(self._episodes, content)
        elif category == "promise":
            self._add_unique(self._promises, content)
        self._save_relationship_memory()

    def capture_relationship_memory(
        self,
        user_message: str,
        assistant_message: str = "",
    ) -> Dict[str, List[str]]:
        """保守抽取一轮对话中的长期关系记忆。"""
        text = user_message.strip()
        captured: Dict[str, List[str]] = {
            "preferences": [],
            "episodes": [],
            "promises": [],
        }
        if not text:
            return captured

        if any(token in text for token in ("我喜欢", "我最喜欢", "我爱喝", "我爱吃", "我不喜欢", "讨厌", "偏好")):
            memory = _compact_memory_text(text)
            self.record_preference(memory)
            captured["preferences"].append(memory)

        if any(token in text for token in ("我答应", "你答应", "说好了", "别忘", "记得提醒", "记得帮我")):
            memory = _compact_memory_text(text)
            self.record_promise(memory)
            captured["promises"].append(memory)

        episode_tokens = ("刚才", "昨晚", "上次", "最近", "我们一起")
        today_episode = "今天" in text and "我" in text and "天气" not in text
        if any(token in text for token in episode_tokens) or today_episode:
            if not captured["preferences"] and not captured["promises"]:
                memory = _compact_memory_text(text)
                self.record_episode(memory)
                captured["episodes"].append(memory)

        return captured

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

    def _load_relationship_memory(self) -> None:
        if not self._relationship_memory_path.exists():
            return
        try:
            data = json.loads(self._relationship_memory_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        self._preferences = _string_list(data.get("preferences", []))
        self._episodes = _string_list(data.get("episodes", []))
        self._promises = _string_list(data.get("promises", []))

    def _save_relationship_memory(self) -> None:
        self._relationship_memory_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "preferences": self._preferences[-200:],
            "episodes": self._episodes[-200:],
            "promises": self._promises[-200:],
        }
        self._relationship_memory_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _add_unique(target: List[str], content: str, limit: int = 200) -> None:
        clean = _compact_memory_text(content)
        if not clean:
            return
        if clean in target:
            target.remove(clean)
        target.append(clean)
        del target[:-limit]


def _string_list(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _compact_memory_text(text: str, limit: int = 160) -> str:
    return " ".join(text.strip().split())[:limit]
