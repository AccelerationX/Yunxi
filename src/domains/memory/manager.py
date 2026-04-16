"""记忆管理器（融合终身学习完整版）。

提供记忆存储、经验记录、技能匹配、失败回放等接口，
并集成 ExperienceBuffer / PatternMiner / SkillDistiller / SkillLibrary / FailureReplay / ParamFiller。
"""

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, List, Optional

from domains.memory.skills.experience_buffer import ExperienceBuffer
from domains.memory.skills.failure_replay import FailureReplay
from domains.memory.skills.param_filler import ParamFiller
from domains.memory.skills.pattern_miner import PatternMiner
from domains.memory.skills.skill_distiller import SkillDistiller
from domains.memory.skills.skill_library import SkillLibrary


@dataclass
class MemoryItem:
    """Typed long-term memory item for daily-mode v2."""

    id: str
    type: str
    content: str
    importance: float
    confidence: float
    source: str
    evidence: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    last_used_at: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    supersedes: Optional[str] = None
    deleted: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        """Build a memory item from persisted JSON data."""
        now = _now_iso()
        return cls(
            id=str(data.get("id") or _memory_id(data.get("type", "note"), data.get("content", ""))),
            type=str(data.get("type") or "note"),
            content=_compact_memory_text(str(data.get("content") or "")),
            importance=float(data.get("importance", 0.5)),
            confidence=float(data.get("confidence", 0.8)),
            source=str(data.get("source") or "legacy"),
            evidence=_string_list(data.get("evidence", [])),
            tags=_string_list(data.get("tags", [])),
            created_at=str(data.get("created_at") or now),
            updated_at=str(data.get("updated_at") or now),
            last_used_at=data.get("last_used_at"),
            valid_from=data.get("valid_from"),
            valid_to=data.get("valid_to"),
            supersedes=data.get("supersedes"),
            deleted=bool(data.get("deleted", False)),
        )


@dataclass
class MemoryCandidate:
    """One lightweight memory candidate extracted from a chat turn."""

    type: str
    content: str
    importance: float
    confidence: float
    tags: List[str] = field(default_factory=list)


@dataclass
class ConversationTurn:
    """One short chat turn kept before session-level summarization."""

    user: str
    assistant: str
    created_at: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationTurn":
        return cls(
            user=_compact_memory_text(str(data.get("user") or ""), limit=240),
            assistant=_compact_memory_text(str(data.get("assistant") or ""), limit=240),
            created_at=str(data.get("created_at") or _now_iso()),
        )


class DailyMemoryAppraiser:
    """Conservative rule-based memory appraiser for the v2 foundation.

    The first implementation is intentionally deterministic and local. It gives
    the runtime a stable typed-memory path before adding optional LLM appraisal.
    """

    def appraise(self, user_message: str, assistant_message: str = "") -> List[MemoryCandidate]:
        text = _compact_memory_text(user_message, limit=240)
        if not text:
            return []

        candidates: List[MemoryCandidate] = []
        self._maybe_add_preference(text, candidates)
        self._maybe_add_promise(text, candidates)
        self._maybe_add_episode(text, candidates)
        self._maybe_add_boundary(text, candidates)
        self._maybe_add_emotion_feedback(text, candidates)
        self._maybe_add_relationship(text, candidates)
        self._maybe_add_interaction_style(text, candidates)
        self._maybe_add_self_memory(text, candidates)
        self._maybe_add_fact(text, candidates)
        return _dedupe_candidates(candidates)

    def _maybe_add_preference(self, text: str, candidates: List[MemoryCandidate]) -> None:
        if any(token in text for token in ("我喜欢", "我最喜欢", "我爱喝", "我爱吃", "我不喜欢", "讨厌", "偏好")):
            candidates.append(MemoryCandidate("preference", text, 0.78, 0.86, ["user_preference"]))

    def _maybe_add_promise(self, text: str, candidates: List[MemoryCandidate]) -> None:
        if any(token in text for token in ("我答应", "你答应", "说好了", "别忘", "记得提醒", "记得帮我")):
            candidates.append(MemoryCandidate("promise", text, 0.86, 0.86, ["promise"]))

    def _maybe_add_episode(self, text: str, candidates: List[MemoryCandidate]) -> None:
        episode_tokens = ("刚才", "昨晚", "上次", "最近", "我们一起")
        today_episode = "今天" in text and "我" in text and "天气" not in text
        if any(token in text for token in episode_tokens) or today_episode:
            candidates.append(MemoryCandidate("episode", text, 0.58, 0.72, ["episode"]))

    def _maybe_add_boundary(self, text: str, candidates: List[MemoryCandidate]) -> None:
        boundary_patterns = (
            "别总", "不要总", "别再", "不要再", "不想让你", "别记", "不要记",
            "少打扰", "别打扰", "不要打扰", "有点烦", "让我不舒服",
        )
        if any(token in text for token in boundary_patterns):
            candidates.append(MemoryCandidate("boundary", text, 0.92, 0.82, ["boundary"]))

    def _maybe_add_emotion_feedback(self, text: str, candidates: List[MemoryCandidate]) -> None:
        feedback_tokens = (
            "让我安心", "有安全感", "被陪着", "陪伴感", "很开心", "我开心",
            "我难过", "我委屈", "我有点难受", "撑不住", "情感寄托",
        )
        if any(token in text for token in feedback_tokens):
            candidates.append(MemoryCandidate("emotion_feedback", text, 0.88, 0.82, ["emotion"]))

    def _maybe_add_relationship(self, text: str, candidates: List[MemoryCandidate]) -> None:
        relationship_tokens = (
            "你是我的", "我的云汐", "不是工具", "情感寄托", "放下伪装",
            "用心相处", "女友", "陪我很重要",
        )
        if any(token in text for token in relationship_tokens):
            candidates.append(MemoryCandidate("relationship", text, 0.9, 0.82, ["relationship"]))

    def _maybe_add_interaction_style(self, text: str, candidates: List[MemoryCandidate]) -> None:
        style_tokens = (
            "希望你", "我希望", "以后你", "喜欢你", "撒娇", "碎碎念",
            "刷存在感", "活泼", "可爱", "不要太正式", "别太正式",
        )
        if any(token in text for token in style_tokens):
            candidates.append(MemoryCandidate("interaction_style", text, 0.8, 0.78, ["style"]))

    def _maybe_add_self_memory(self, text: str, candidates: List[MemoryCandidate]) -> None:
        self_tokens = ("云汐学会", "云汐完成", "我们把云汐", "日常模式", "心湖系统", "记忆系统")
        if any(token in text for token in self_tokens):
            candidates.append(MemoryCandidate("self_memory", text, 0.68, 0.74, ["yunxi_growth"]))

    def _maybe_add_fact(self, text: str, candidates: List[MemoryCandidate]) -> None:
        if re.search(r"我(叫|是|在|住|来自|正在|学|做|负责)", text):
            if not any(c.type in {"preference", "promise", "boundary"} for c in candidates):
                candidates.append(MemoryCandidate("fact", text, 0.66, 0.72, ["user_fact"]))


class DailyMemorySummarizer:
    """Deterministic session summarizer for memory v2 stage two.

    This is the local fallback before LLM summarization. It compresses several
    turns into typed summary candidates so long chats do not rely only on the
    last few raw messages.
    """

    def summarize(self, turns: List[ConversationTurn]) -> List[MemoryCandidate]:
        active_turns = [turn for turn in turns if turn.user.strip()]
        if not active_turns:
            return []

        user_texts = [turn.user for turn in active_turns]
        joined = " ".join(user_texts)
        candidates = [
            MemoryCandidate(
                "summary",
                "最近一段对话里，远主要聊到：" + "；".join(_summary_fragments(user_texts, limit=4)),
                0.62,
                0.76,
                ["conversation_summary"],
            )
        ]

        emotion_fragments = [
            text for text in user_texts
            if any(token in text for token in ("累", "难过", "委屈", "安心", "开心", "撑不住", "陪伴", "焦虑"))
        ]
        if emotion_fragments:
            candidates.append(
                MemoryCandidate(
                    "emotion_summary",
                    "最近一段对话中，远的情绪线索：" + "；".join(_summary_fragments(emotion_fragments, limit=3)),
                    0.72,
                    0.78,
                    ["emotion_summary"],
                )
            )

        if any(token in joined for token in ("情感寄托", "不是工具", "女友", "陪我", "放下伪装", "用心相处")):
            candidates.append(
                MemoryCandidate(
                    "relationship",
                    "最近一段对话强化了关系线索：" + "；".join(_summary_fragments(user_texts, limit=3)),
                    0.82,
                    0.78,
                    ["relationship_summary"],
                )
            )

        if any(token in joined for token in ("希望你", "我希望", "以后你", "碎碎念", "刷存在感", "别打扰", "不要太正式")):
            candidates.append(
                MemoryCandidate(
                    "interaction_style",
                    "最近一段对话更新了远偏好的互动方式：" + "；".join(_summary_fragments(user_texts, limit=3)),
                    0.78,
                    0.78,
                    ["style_summary"],
                )
            )

        return _dedupe_candidates(candidates)


class PromptMemoryCompiler:
    """Compile relationship memory into a bounded prompt summary."""

    def compile(
        self,
        preferences: List[str],
        episodes: List[str],
        promises: List[str],
        memory_items: List[MemoryItem],
        limit: int,
        query: str = "",
    ) -> str:
        lines: List[str] = []
        if preferences:
            lines.append("远的偏好：" + "；".join(preferences[-limit:]))
        if episodes:
            lines.append("共同经历：" + "；".join(episodes[-limit:]))
        if promises:
            lines.append("承诺：" + "；".join(promises[-limit:]))

        typed_lines = self._compile_typed(
            preferences=preferences,
            episodes=episodes,
            promises=promises,
            memory_items=memory_items,
            limit=limit,
            query=query,
        )
        lines.extend(typed_lines)
        return "\n".join(lines)

    def _compile_typed(
        self,
        preferences: List[str],
        episodes: List[str],
        promises: List[str],
        memory_items: List[MemoryItem],
        limit: int,
        query: str = "",
    ) -> List[str]:
        grouped: Dict[str, List[MemoryItem]] = {}
        legacy_contents = {
            "preference": set(preferences),
            "episode": set(episodes),
            "promise": set(promises),
        }
        for item in self._rank_memory_items(memory_items, query=query):
            if item.content in legacy_contents.get(item.type, set()):
                continue
            grouped.setdefault(item.type, []).append(item)

        lines: List[str] = []
        remaining = max(0, limit)
        for memory_type in _MEMORY_SUMMARY_ORDER:
            if remaining <= 0:
                break
            items = grouped.get(memory_type, [])
            if not items:
                continue
            selected = items[:remaining]
            label = _MEMORY_LABELS.get(memory_type, memory_type)
            lines.append(f"{label}：" + "；".join(item.content for item in selected))
            now = _now_iso()
            for item in selected:
                item.last_used_at = now
            remaining -= len(selected)
        return lines

    def _rank_memory_items(self, memory_items: List[MemoryItem], query: str = "") -> List[MemoryItem]:
        terms = _query_terms(query)
        active = [item for item in memory_items if not item.deleted]

        def score(item: MemoryItem) -> float:
            base = item.importance * 2 + item.confidence
            if terms and _matches_terms(item.content, terms):
                base += 2.0
            if item.type in {"core", "boundary", "promise", "relationship", "emotion_feedback"}:
                base += 0.5
            return base

        return sorted(active, key=score, reverse=True)


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
        self._memory_items: List[MemoryItem] = []
        self._conversation_turn_buffer: List[ConversationTurn] = []
        self._memory_appraiser = DailyMemoryAppraiser()
        self._memory_summarizer = DailyMemorySummarizer()
        self._prompt_memory_compiler = PromptMemoryCompiler()
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
        self.add_typed_memory("preference", content, importance=0.78, confidence=0.86, source="manual")
        self._save_relationship_memory()

    def record_episode(self, content: str) -> None:
        """记录事件片段。"""
        self._add_unique(self._episodes, content)
        self.add_typed_memory("episode", content, importance=0.58, confidence=0.75, source="manual")
        self._save_relationship_memory()

    def record_promise(self, content: str) -> None:
        """记录承诺。"""
        self._add_unique(self._promises, content)
        self.add_typed_memory("promise", content, importance=0.86, confidence=0.86, source="manual")
        self._save_relationship_memory()

    def add_raw_memory(self, category: str, content: str) -> None:
        """按分类写入原始记忆。"""
        if category == "preference":
            self.record_preference(content)
        elif category == "episode":
            self.record_episode(content)
        elif category == "promise":
            self.record_promise(content)
        else:
            self.add_typed_memory(category, content, source="manual")
            self._save_relationship_memory()

    def add_typed_memory(
        self,
        memory_type: str,
        content: str,
        importance: float = 0.6,
        confidence: float = 0.8,
        source: str = "chat",
        evidence: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        supersedes: Optional[str] = None,
    ) -> Optional[MemoryItem]:
        """Add or refresh one typed long-term memory item."""
        clean = _compact_memory_text(content)
        if not clean:
            return None
        memory_type = _normalize_memory_type(memory_type)
        now = _now_iso()
        existing = self._find_exact_memory(memory_type, clean)
        if existing:
            existing.importance = max(existing.importance, float(importance))
            existing.confidence = max(existing.confidence, float(confidence))
            existing.updated_at = now
            existing.deleted = False
            existing.tags = _merged_strings(existing.tags, tags or [])
            existing.evidence = _merged_strings(existing.evidence, evidence or [clean])
            if supersedes:
                existing.supersedes = supersedes
            return existing

        item = MemoryItem(
            id=_memory_id(memory_type, clean),
            type=memory_type,
            content=clean,
            importance=float(importance),
            confidence=float(confidence),
            source=source,
            evidence=_string_list(evidence or [clean]),
            tags=_string_list(tags or []),
            created_at=now,
            updated_at=now,
            valid_from=now,
            supersedes=supersedes,
        )
        self._memory_items.append(item)
        self._memory_items = self._memory_items[-1000:]
        return item

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
            "typed": [],
            "corrections": [],
        }
        if not text:
            return captured

        correction = self._capture_memory_correction(text)
        if correction:
            captured["corrections"].append(correction)

        if any(token in text for token in ("我喜欢", "我最喜欢", "我爱喝", "我爱吃", "我不喜欢", "讨厌", "偏好")):
            memory = _compact_memory_text(text)
            self._add_unique(self._preferences, memory)
            captured["preferences"].append(memory)

        if any(token in text for token in ("我答应", "你答应", "说好了", "别忘", "记得提醒", "记得帮我")):
            memory = _compact_memory_text(text)
            self._add_unique(self._promises, memory)
            captured["promises"].append(memory)

        episode_tokens = ("刚才", "昨晚", "上次", "最近", "我们一起")
        today_episode = "今天" in text and "我" in text and "天气" not in text
        if any(token in text for token in episode_tokens) or today_episode:
            if not captured["preferences"] and not captured["promises"]:
                memory = _compact_memory_text(text)
                self._add_unique(self._episodes, memory)
                captured["episodes"].append(memory)

        for candidate in self._memory_appraiser.appraise(user_message, assistant_message):
            item = self.add_typed_memory(
                candidate.type,
                candidate.content,
                importance=candidate.importance,
                confidence=candidate.confidence,
                source="chat",
                evidence=[text],
                tags=candidate.tags,
            )
            if item:
                captured["typed"].append(item.type)

        summary_items = self.record_conversation_turn(user_message, assistant_message)
        if summary_items:
            captured["typed"].extend([item.type for item in summary_items])

        self._save_relationship_memory()

        return captured

    def get_memory_summary(self, limit: int = 10, query: str = "") -> str:
        """获取记忆摘要文本。"""
        return self._prompt_memory_compiler.compile(
            preferences=self._preferences,
            episodes=self._episodes,
            promises=self._promises,
            memory_items=self._memory_items,
            limit=limit,
            query=query,
        )

    def record_conversation_turn(
        self,
        user_message: str,
        assistant_message: str = "",
        summarize_threshold: int = 6,
    ) -> List[MemoryItem]:
        """Record one turn into the session buffer and summarize when needed."""
        user = _compact_memory_text(user_message, limit=240)
        assistant = _compact_memory_text(assistant_message, limit=240)
        if not user and not assistant:
            return []
        self._conversation_turn_buffer.append(
            ConversationTurn(user=user, assistant=assistant, created_at=_now_iso())
        )
        self._conversation_turn_buffer = self._conversation_turn_buffer[-40:]
        if len(self._conversation_turn_buffer) >= summarize_threshold:
            return self.flush_conversation_summary(min_turns=summarize_threshold)
        return []

    def flush_conversation_summary(self, min_turns: int = 2) -> List[MemoryItem]:
        """Compress buffered turns into typed summary memories."""
        if len(self._conversation_turn_buffer) < min_turns:
            return []
        turns = list(self._conversation_turn_buffer)
        self._conversation_turn_buffer.clear()
        items: List[MemoryItem] = []
        evidence = [turn.user for turn in turns if turn.user]
        for candidate in self._memory_summarizer.summarize(turns):
            item = self.add_typed_memory(
                candidate.type,
                candidate.content,
                importance=candidate.importance,
                confidence=candidate.confidence,
                source="conversation_summary",
                evidence=evidence,
                tags=candidate.tags,
            )
            if item:
                items.append(item)
        self._save_relationship_memory()
        return items

    def get_typed_memories(
        self,
        memory_type: Optional[str] = None,
        include_deleted: bool = False,
    ) -> List[MemoryItem]:
        """Return typed memory items, newest first."""
        items = self._memory_items
        if memory_type:
            normalized = _normalize_memory_type(memory_type)
            items = [item for item in items if item.type == normalized]
        if not include_deleted:
            items = [item for item in items if not item.deleted]
        return sorted(items, key=lambda item: item.updated_at or item.created_at, reverse=True)

    def forget_memory(self, query: str, memory_type: Optional[str] = None) -> int:
        """Soft-delete memories matching a natural-language query."""
        terms = _query_terms(query)
        if not terms:
            return 0
        now = _now_iso()
        count = 0
        normalized_type = _normalize_memory_type(memory_type) if memory_type else None
        for item in self._memory_items:
            if item.deleted:
                continue
            if normalized_type and item.type != normalized_type:
                continue
            if _matches_terms(item.content, terms):
                item.deleted = True
                item.valid_to = now
                item.updated_at = now
                count += 1
        if count:
            self._save_relationship_memory()
        return count

    def correct_memory(
        self,
        old_query: str,
        new_content: str,
        memory_type: Optional[str] = None,
    ) -> Optional[MemoryItem]:
        """Supersede a matching memory item with a corrected item."""
        terms = _query_terms(old_query)
        normalized_type = _normalize_memory_type(memory_type) if memory_type else None
        target: Optional[MemoryItem] = None
        for item in self.get_typed_memories(include_deleted=False):
            if normalized_type and item.type != normalized_type:
                continue
            if _matches_terms(item.content, terms):
                target = item
                break
        if target is None:
            corrected_type = normalized_type or "fact"
            item = self.add_typed_memory(
                corrected_type,
                new_content,
                importance=0.74,
                confidence=0.78,
                source="correction",
            )
            self._save_relationship_memory()
            return item

        now = _now_iso()
        target.valid_to = now
        target.deleted = True
        target.updated_at = now
        item = self.add_typed_memory(
            target.type,
            new_content,
            importance=max(target.importance, 0.78),
            confidence=0.9,
            source="correction",
            supersedes=target.id,
            tags=_merged_strings(target.tags, ["correction"]),
        )
        self._save_relationship_memory()
        return item

    def export_memory_markdown(self) -> str:
        """Export readable relationship memory for manual inspection."""
        sections = ["# 云汐长期记忆导出", ""]
        grouped: Dict[str, List[MemoryItem]] = {}
        for item in self.get_typed_memories(include_deleted=False):
            grouped.setdefault(item.type, []).append(item)
        for memory_type in _MEMORY_SUMMARY_ORDER:
            items = grouped.get(memory_type, [])
            if not items:
                continue
            sections.append(f"## {memory_type}")
            for item in items:
                sections.append(f"- {item.content} _(importance={item.importance:.2f}, confidence={item.confidence:.2f})_")
            sections.append("")
        return "\n".join(sections).strip() + "\n"

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

    def list_skill_candidates(self) -> List[Dict[str, Any]]:
        """List mined skills waiting for user approval."""
        return self.skill_library.list_skills(status="pending")

    def approve_skill_candidate(self, skill_name: str) -> bool:
        """Approve a pending skill candidate so it can be used."""
        return self.skill_library.approve_candidate(skill_name)

    def reject_skill_candidate(self, skill_name: str) -> bool:
        """Reject a pending skill candidate."""
        return self.skill_library.reject_candidate(skill_name)

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

            existing = self.skill_library.list_skills()
            if any(item["skill_name"] == skill["skill_name"] for item in existing):
                continue

            self.skill_library.add_candidate(
                skill,
                reason=(
                    f"从 {pattern.get('size', 0)} 条相似经验中挖掘，"
                    f"confidence={pattern.get('confidence', 0):.2f}"
                ),
            )

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
        self._memory_items = []
        for raw_item in data.get("memory_items", []):
            if not isinstance(raw_item, dict):
                continue
            item = MemoryItem.from_dict(raw_item)
            if item.content:
                self._memory_items.append(item)
        self._conversation_turn_buffer = []
        for raw_turn in data.get("conversation_turn_buffer", []):
            if not isinstance(raw_turn, dict):
                continue
            turn = ConversationTurn.from_dict(raw_turn)
            if turn.user or turn.assistant:
                self._conversation_turn_buffer.append(turn)
        self._ensure_legacy_items()

    def _save_relationship_memory(self) -> None:
        self._relationship_memory_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_legacy_items()
        payload = {
            "version": 2,
            "preferences": self._preferences[-200:],
            "episodes": self._episodes[-200:],
            "promises": self._promises[-200:],
            "memory_items": [
                asdict(item)
                for item in sorted(
                    self._memory_items,
                    key=lambda memory: memory.updated_at or memory.created_at,
                )[-1000:]
            ],
            "conversation_turn_buffer": [
                asdict(turn) for turn in self._conversation_turn_buffer[-40:]
            ],
        }
        self._relationship_memory_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _ensure_legacy_items(self) -> None:
        """Mirror legacy lists into typed memory items for v2 compatibility."""
        for content in self._preferences:
            self.add_typed_memory("preference", content, importance=0.78, confidence=0.86, source="legacy")
        for content in self._episodes:
            self.add_typed_memory("episode", content, importance=0.58, confidence=0.75, source="legacy")
        for content in self._promises:
            self.add_typed_memory("promise", content, importance=0.86, confidence=0.86, source="legacy")

    def _find_exact_memory(self, memory_type: str, content: str) -> Optional[MemoryItem]:
        for item in self._memory_items:
            if item.type == memory_type and item.content == content:
                return item
        return None

    def _capture_memory_correction(self, text: str) -> str:
        if any(token in text for token in ("别记", "不要记", "不想让你记")):
            forgotten = self.forget_memory(text)
            return f"forgot:{forgotten}"
        if any(token in text for token in ("你记错", "记错了", "不是这个意思", "不是那样")):
            item = self.add_typed_memory(
                "boundary",
                text,
                importance=0.9,
                confidence=0.8,
                source="correction",
                tags=["memory_correction"],
            )
            self._save_relationship_memory()
            return f"correction:{item.id if item else ''}"
        return ""

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


_MEMORY_SUMMARY_ORDER = [
    "core",
    "boundary",
    "relationship",
    "emotion_feedback",
    "interaction_style",
    "summary",
    "emotion_summary",
    "preference",
    "episode",
    "promise",
    "fact",
    "self_memory",
    "open_topic",
    "procedural",
    "resource",
    "failure",
]

_MEMORY_LABELS = {
    "core": "核心记忆",
    "fact": "远的事实",
    "relationship": "关系记忆",
    "emotion_feedback": "情绪反馈",
    "emotion_summary": "情绪摘要",
    "boundary": "互动边界",
    "interaction_style": "互动风格",
    "summary": "会话摘要",
    "self_memory": "云汐成长记忆",
    "open_topic": "开放话题",
    "procedural": "程序性记忆",
    "resource": "资源记忆",
    "failure": "失败经验",
    "preference": "远的偏好",
    "episode": "共同经历",
    "promise": "承诺",
}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _memory_id(memory_type: str, content: str) -> str:
    digest = sha1(f"{memory_type}:{_compact_memory_text(content)}".encode("utf-8")).hexdigest()[:16]
    return f"mem_{digest}"


def _normalize_memory_type(memory_type: str) -> str:
    mapping = {
        "preferences": "preference",
        "episodes": "episode",
        "promises": "promise",
        "style": "interaction_style",
        "emotion": "emotion_feedback",
        "tool": "procedural",
    }
    clean = str(memory_type or "note").strip().lower()
    return mapping.get(clean, clean)


def _merged_strings(left: List[str], right: List[str]) -> List[str]:
    merged: List[str] = []
    for item in list(left) + list(right):
        clean = str(item).strip()
        if clean and clean not in merged:
            merged.append(clean)
    return merged[-20:]


def _dedupe_candidates(candidates: List[MemoryCandidate]) -> List[MemoryCandidate]:
    result: List[MemoryCandidate] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        key = (candidate.type, candidate.content)
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def _query_terms(query: str) -> List[str]:
    text = _compact_memory_text(query, limit=240).lower()
    if not text:
        return []
    ascii_terms = re.findall(r"[a-z0-9_./\\-]{2,}", text)
    chinese_terms = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    short_chinese: List[str] = []
    for term in chinese_terms:
        if len(term) <= 8:
            short_chinese.append(term)
        else:
            short_chinese.extend(term[i : i + 4] for i in range(0, len(term) - 3, 2))
    return _merged_strings(ascii_terms, short_chinese)


def _matches_terms(content: str, terms: List[str]) -> bool:
    if not terms:
        return False
    lowered = content.lower()
    return any(term in lowered for term in terms)


def _summary_fragments(texts: List[str], limit: int) -> List[str]:
    fragments: List[str] = []
    for text in texts:
        clean = _compact_memory_text(text, limit=80)
        if clean and clean not in fragments:
            fragments.append(clean)
        if len(fragments) >= limit:
            break
    return fragments
