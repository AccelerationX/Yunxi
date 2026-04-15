"""Conversation continuity service for Yunxi."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional


DEFAULT_MAX_EXCHANGES = 50
DEFAULT_SUMMARY_LIMIT = 20
DEFAULT_MAX_OPEN_THREADS = 12
DEFAULT_MAX_RECENT_TOPICS = 20

logger = logging.getLogger(__name__)


@dataclass
class ConversationExchange:
    """One user/Yunxi exchange stored in continuity."""

    user_message: str
    assistant_message: str
    proactive: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, object]:
        """Serialize the exchange to JSON-compatible data."""
        return {
            "user_message": self.user_message,
            "assistant_message": self.assistant_message,
            "proactive": self.proactive,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ConversationExchange":
        """Deserialize an exchange from JSON-compatible data."""
        return cls(
            user_message=str(data.get("user_message", "")),
            assistant_message=str(data.get("assistant_message", "")),
            proactive=bool(data.get("proactive", False)),
            timestamp=float(data.get("timestamp", time.time())),
        )


@dataclass
class OpenThread:
    """An unfinished relationship or conversation thread."""

    title: str
    detail: str = ""
    status: str = "open"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, object]:
        """Serialize the thread to JSON-compatible data."""
        return {
            "title": self.title,
            "detail": self.detail,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "OpenThread":
        """Deserialize an open thread from JSON-compatible data."""
        return cls(
            title=str(data.get("title", "")),
            detail=str(data.get("detail", "")),
            status=str(data.get("status", "open")),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )


@dataclass
class CompanionContinuityService:
    """Maintain recent conversation, open threads, and persistent summaries."""

    max_exchanges: int = DEFAULT_MAX_EXCHANGES
    storage_path: Optional[Path | str] = None
    exchanges: List[ConversationExchange] = field(default_factory=list)
    unanswered_proactive_count: int = 0
    recent_proactive_count: int = 0
    relationship_summary: str = ""
    emotional_summary: str = ""
    user_style_summary: str = ""
    open_threads: List[OpenThread] = field(default_factory=list)
    proactive_cues: List[str] = field(default_factory=list)
    recent_topics: List[str] = field(default_factory=list)
    user_returned_recently: bool = False
    comfort_needed: bool = False
    task_focus: str = ""
    fragmented_chat: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.storage_path, str):
            self.storage_path = Path(self.storage_path)
        if self.storage_path is not None and self.storage_path.exists():
            self._load()

    def record_exchange(
        self,
        user_message: str,
        assistant_message: str,
        proactive: bool = False,
    ) -> None:
        """Record one complete exchange and persist continuity state."""
        self.exchanges.append(
            ConversationExchange(
                user_message=user_message,
                assistant_message=assistant_message,
                proactive=proactive,
            )
        )
        if proactive:
            self.unanswered_proactive_count += 1
            self.recent_proactive_count += 1
        elif user_message:
            self.unanswered_proactive_count = 0
            self.user_returned_recently = True

        self._capture_recent_topic(user_message or assistant_message)
        self._trim()
        self.save()

    def record_assistant_message(self, message: str, proactive: bool = False) -> None:
        """Record an assistant message without a paired user input."""
        self.record_exchange("", message, proactive=proactive)

    def add_open_thread(self, title: str, detail: str = "") -> None:
        """Add or update an unfinished conversation thread."""
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("open thread title must not be empty")

        now = time.time()
        for thread in self.open_threads:
            if thread.title == clean_title:
                thread.detail = detail.strip() or thread.detail
                thread.status = "open"
                thread.updated_at = now
                self.save()
                return

        self.open_threads.append(
            OpenThread(
                title=clean_title,
                detail=detail.strip(),
                status="open",
                created_at=now,
                updated_at=now,
            )
        )
        self.open_threads = self.open_threads[-DEFAULT_MAX_OPEN_THREADS:]
        self.save()

    def resolve_open_thread(self, title: str) -> None:
        """Mark an open thread as resolved."""
        clean_title = title.strip()
        for thread in self.open_threads:
            if thread.title == clean_title:
                thread.status = "resolved"
                thread.updated_at = time.time()
                self.save()
                return

    def get_open_threads(self) -> list[OpenThread]:
        """Return unresolved open threads."""
        return [thread for thread in self.open_threads if thread.status == "open"]

    def add_proactive_cue(self, cue: str) -> None:
        """Store a future proactive conversation cue."""
        clean_cue = cue.strip()
        if not clean_cue:
            raise ValueError("proactive cue must not be empty")
        if clean_cue not in self.proactive_cues:
            self.proactive_cues.append(clean_cue)
            self.proactive_cues = self.proactive_cues[-DEFAULT_MAX_RECENT_TOPICS:]
            self.save()

    def update_summaries(
        self,
        *,
        relationship_summary: Optional[str] = None,
        emotional_summary: Optional[str] = None,
        user_style_summary: Optional[str] = None,
    ) -> None:
        """Update persistent relationship, emotion, and user-style summaries."""
        if relationship_summary is not None:
            self.relationship_summary = relationship_summary.strip()
        if emotional_summary is not None:
            self.emotional_summary = emotional_summary.strip()
        if user_style_summary is not None:
            self.user_style_summary = user_style_summary.strip()
        self.save()

    def set_flags(
        self,
        *,
        comfort_needed: Optional[bool] = None,
        task_focus: Optional[str] = None,
        fragmented_chat: Optional[bool] = None,
    ) -> None:
        """Update persistent contextual flags used by initiative decisions."""
        if comfort_needed is not None:
            self.comfort_needed = comfort_needed
        if task_focus is not None:
            self.task_focus = task_focus.strip()
        if fragmented_chat is not None:
            self.fragmented_chat = fragmented_chat
        self.save()

    def get_recent_exchanges(self, limit: int = DEFAULT_SUMMARY_LIMIT) -> List[ConversationExchange]:
        """Return recent conversation exchanges."""
        return self.exchanges[-limit:]

    def get_summary(self, limit: int = DEFAULT_SUMMARY_LIMIT) -> str:
        """Build a continuity summary for prompt injection."""
        lines: List[str] = []
        if self.relationship_summary:
            lines.append(f"relationship_summary: {self.relationship_summary}")
        if self.emotional_summary:
            lines.append(f"emotional_summary: {self.emotional_summary}")
        if self.user_style_summary:
            lines.append(f"user_style_summary: {self.user_style_summary}")

        open_threads = self.get_open_threads()
        if open_threads:
            lines.append("open_threads:")
            for thread in open_threads:
                detail = f" - {thread.detail}" if thread.detail else ""
                lines.append(f"- {thread.title}{detail}")

        if self.recent_topics:
            lines.append("recent_topics: " + " / ".join(self.recent_topics[-6:]))
        if self.proactive_cues:
            lines.append("proactive_cues: " + " / ".join(self.proactive_cues[-6:]))

        if self.comfort_needed:
            lines.append("comfort_needed: true")
        if self.task_focus:
            lines.append(f"task_focus: {self.task_focus}")
        if self.fragmented_chat:
            lines.append("fragmented_chat: true")

        for exchange in self.get_recent_exchanges(limit):
            if exchange.user_message:
                lines.append(f"远：{exchange.user_message}")
            label = "云汐（主动）" if exchange.proactive else "云汐"
            if exchange.assistant_message:
                lines.append(f"{label}：{exchange.assistant_message}")
        return "\n".join(lines)

    def reset(self) -> None:
        """Clear continuity state and persist the cleared state."""
        self.exchanges.clear()
        self.unanswered_proactive_count = 0
        self.recent_proactive_count = 0
        self.relationship_summary = ""
        self.emotional_summary = ""
        self.user_style_summary = ""
        self.open_threads.clear()
        self.proactive_cues.clear()
        self.recent_topics.clear()
        self.user_returned_recently = False
        self.comfort_needed = False
        self.task_focus = ""
        self.fragmented_chat = False
        self.save()

    def save(self) -> None:
        """Persist continuity state when a storage path is configured."""
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.storage_path.write_text(
                json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to persist continuity state to %s: %s", self.storage_path, exc)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full continuity state."""
        return {
            "version": 1,
            "max_exchanges": self.max_exchanges,
            "exchanges": [exchange.to_dict() for exchange in self.exchanges],
            "unanswered_proactive_count": self.unanswered_proactive_count,
            "recent_proactive_count": self.recent_proactive_count,
            "relationship_summary": self.relationship_summary,
            "emotional_summary": self.emotional_summary,
            "user_style_summary": self.user_style_summary,
            "open_threads": [thread.to_dict() for thread in self.open_threads],
            "proactive_cues": self.proactive_cues,
            "recent_topics": self.recent_topics,
            "user_returned_recently": self.user_returned_recently,
            "comfort_needed": self.comfort_needed,
            "task_focus": self.task_focus,
            "fragmented_chat": self.fragmented_chat,
        }

    def _load(self) -> None:
        if self.storage_path is None:
            return
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load continuity state from %s: %s", self.storage_path, exc)
            return

        if not isinstance(data, dict):
            logger.warning("Continuity state root must be an object: %s", self.storage_path)
            return

        self.max_exchanges = int(data.get("max_exchanges", self.max_exchanges))
        self.exchanges = [
            ConversationExchange.from_dict(item)
            for item in data.get("exchanges", [])
            if isinstance(item, dict)
        ]
        self.unanswered_proactive_count = int(data.get("unanswered_proactive_count", 0))
        self.recent_proactive_count = int(data.get("recent_proactive_count", 0))
        self.relationship_summary = str(data.get("relationship_summary", ""))
        self.emotional_summary = str(data.get("emotional_summary", ""))
        self.user_style_summary = str(data.get("user_style_summary", ""))
        self.open_threads = [
            OpenThread.from_dict(item)
            for item in data.get("open_threads", [])
            if isinstance(item, dict)
        ]
        self.proactive_cues = _string_list(data.get("proactive_cues", []))
        self.recent_topics = _string_list(data.get("recent_topics", []))
        self.user_returned_recently = bool(data.get("user_returned_recently", False))
        self.comfort_needed = bool(data.get("comfort_needed", False))
        self.task_focus = str(data.get("task_focus", ""))
        self.fragmented_chat = bool(data.get("fragmented_chat", False))
        self._trim()

    def _capture_recent_topic(self, text: str) -> None:
        topic = text.strip().replace("\n", " ")
        if not topic:
            return
        topic = topic[:80]
        if topic in self.recent_topics:
            self.recent_topics.remove(topic)
        self.recent_topics.append(topic)
        self.recent_topics = self.recent_topics[-DEFAULT_MAX_RECENT_TOPICS:]

    def _trim(self) -> None:
        if len(self.exchanges) > self.max_exchanges:
            self.exchanges = self.exchanges[-self.max_exchanges :]
        self.open_threads = self.open_threads[-DEFAULT_MAX_OPEN_THREADS:]
        self.recent_topics = self.recent_topics[-DEFAULT_MAX_RECENT_TOPICS:]
        self.proactive_cues = self.proactive_cues[-DEFAULT_MAX_RECENT_TOPICS:]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
