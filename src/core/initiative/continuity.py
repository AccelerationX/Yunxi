"""Conversation continuity service for Yunxi."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional


DEFAULT_MAX_EXCHANGES = 50
DEFAULT_SUMMARY_LIMIT = 20
DEFAULT_MAX_OPEN_THREADS = 12
DEFAULT_MAX_RECENT_TOPICS = 20
DEFAULT_MAX_RECENT_PRESENCE_MURMURS = 10000
DEFAULT_DAILY_PRESENCE_MURMUR_BUDGET = 6
DEFAULT_PRESENCE_MURMUR_COOLDOWN_SECONDS = 900.0

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
class InitiativeEventRecord:
    """A selected proactive event recorded for relationship continuity."""

    event_id: str
    category: str
    seed: str
    affect_valence: float = 0.0
    affect_arousal: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, object]:
        """Serialize the event record to JSON-compatible data."""
        return {
            "event_id": self.event_id,
            "category": self.category,
            "seed": self.seed,
            "affect_valence": self.affect_valence,
            "affect_arousal": self.affect_arousal,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "InitiativeEventRecord":
        """Deserialize an initiative event record."""
        return cls(
            event_id=str(data.get("event_id", "")),
            category=str(data.get("category", "")),
            seed=str(data.get("seed", "")),
            affect_valence=float(data.get("affect_valence", 0.0)),
            affect_arousal=float(data.get("affect_arousal", 0.0)),
            timestamp=float(data.get("timestamp", time.time())),
        )


@dataclass
class CompanionContinuityService:
    """Maintain recent conversation, open threads, and persistent summaries."""

    max_exchanges: int = DEFAULT_MAX_EXCHANGES
    storage_path: Optional[Path | str] = None
    exchanges: List[ConversationExchange] = field(default_factory=list)
    unanswered_proactive_count: int = 0
    recent_proactive_count: int = 0
    proactive_count_date: str = ""
    relationship_summary: str = ""
    emotional_summary: str = ""
    user_style_summary: str = ""
    open_threads: List[OpenThread] = field(default_factory=list)
    initiative_events: List[InitiativeEventRecord] = field(default_factory=list)
    proactive_cues: List[str] = field(default_factory=list)
    recent_topics: List[str] = field(default_factory=list)
    user_returned_recently: bool = False
    comfort_needed: bool = False
    task_focus: str = ""
    fragmented_chat: bool = False
    presence_murmur_count: int = 0
    presence_murmur_count_date: str = ""
    last_presence_murmur_at: float = 0.0
    recent_presence_murmurs: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.storage_path, str):
            self.storage_path = Path(self.storage_path)
        if self.storage_path is not None and self.storage_path.exists():
            self._load()
        if not self.proactive_count_date:
            self.proactive_count_date = _date_key()
        if not self.presence_murmur_count_date:
            self.presence_murmur_count_date = _date_key()

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
            self.refresh_daily_proactive_count()
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

    def refresh_daily_proactive_count(self, current_time: Optional[float] = None) -> None:
        """Reset proactive budget counter when the local date changes."""
        today = _date_key(current_time)
        if not self.proactive_count_date:
            self.proactive_count_date = today
            return
        if self.proactive_count_date != today:
            self.proactive_count_date = today
            self.recent_proactive_count = 0
            self.save()

    def refresh_daily_presence_murmur_count(
        self,
        current_time: Optional[float] = None,
    ) -> None:
        """Reset the presence-murmur budget counter when the local date changes."""
        today = _date_key(current_time)
        if not self.presence_murmur_count_date:
            self.presence_murmur_count_date = today
            return
        if self.presence_murmur_count_date != today:
            self.presence_murmur_count_date = today
            self.presence_murmur_count = 0
            self.save()

    def can_send_presence_murmur(
        self,
        current_time: Optional[float] = None,
        *,
        cooldown_seconds: float = DEFAULT_PRESENCE_MURMUR_COOLDOWN_SECONDS,
        daily_budget: int = DEFAULT_DAILY_PRESENCE_MURMUR_BUDGET,
    ) -> bool:
        """Return whether a low-cost presence murmur can be sent now."""
        now = current_time if current_time is not None else time.time()
        self.refresh_daily_presence_murmur_count(now)
        if self.presence_murmur_count >= daily_budget:
            return False
        if (
            self.last_presence_murmur_at > 0
            and now - self.last_presence_murmur_at < cooldown_seconds
        ):
            return False
        return True

    def presence_murmur_suppression_reason(
        self,
        current_time: Optional[float] = None,
        *,
        cooldown_seconds: float = DEFAULT_PRESENCE_MURMUR_COOLDOWN_SECONDS,
        daily_budget: int = DEFAULT_DAILY_PRESENCE_MURMUR_BUDGET,
    ) -> str:
        """Explain why a presence murmur is currently unavailable."""
        now = current_time if current_time is not None else time.time()
        self.refresh_daily_presence_murmur_count(now)
        if self.presence_murmur_count >= daily_budget:
            return "presence_murmur_daily_budget_exhausted"
        if (
            self.last_presence_murmur_at > 0
            and now - self.last_presence_murmur_at < cooldown_seconds
        ):
            return "presence_murmur_cooldown"
        return ""

    def has_recent_presence_murmur(self, message: str) -> bool:
        """Return whether this exact murmur sentence has been used recently."""
        normalized = _normalize_presence_murmur(message)
        if not normalized:
            return False
        return normalized in self.recent_presence_murmurs

    def record_presence_murmur(
        self,
        message: str,
        current_time: Optional[float] = None,
    ) -> None:
        """Record one delivered presence murmur for uniqueness and budgeting."""
        normalized = _normalize_presence_murmur(message)
        if not normalized:
            return
        now = current_time if current_time is not None else time.time()
        self.refresh_daily_presence_murmur_count(now)
        if normalized in self.recent_presence_murmurs:
            self.recent_presence_murmurs.remove(normalized)
        self.recent_presence_murmurs.append(normalized)
        self.recent_presence_murmurs = self.recent_presence_murmurs[
            -DEFAULT_MAX_RECENT_PRESENCE_MURMURS:
        ]
        self.presence_murmur_count += 1
        self.last_presence_murmur_at = now
        self.save()

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

    def record_initiative_event(
        self,
        *,
        event_id: str,
        category: str,
        seed: str,
        affect_valence: float = 0.0,
        affect_arousal: float = 0.0,
    ) -> None:
        """Record a selected initiative event for continuity."""
        clean_seed = seed.strip()
        if not clean_seed:
            return
        record = InitiativeEventRecord(
            event_id=event_id.strip(),
            category=category.strip(),
            seed=clean_seed[:160],
            affect_valence=affect_valence,
            affect_arousal=affect_arousal,
        )
        self.initiative_events.append(record)
        self.initiative_events = self.initiative_events[-DEFAULT_MAX_RECENT_TOPICS:]
        self._capture_recent_topic(f"initiative:{record.category}:{record.seed}")
        self.save()

    def capture_user_continuity(self, user_message: str) -> None:
        """Extract conservative continuity cues from one user message."""
        text = user_message.strip()
        if not text:
            return

        changed = False
        if any(token in text for token in ("累", "难过", "焦虑", "崩溃", "压力", "撑不住", "睡不着", "失眠")):
            self.comfort_needed = True
            changed = True
        if any(token in text for token in ("改代码", "修复", "排查", "测试", "部署", "方案", "规划")):
            self.task_focus = _compact_text(text, 80)
            changed = True

        future_tokens = ("明天", "下次", "回头", "之后", "晚点", "待会", "一会儿", "以后")
        action_tokens = ("提醒", "继续", "再聊", "看看", "处理", "记得", "跟进", "复盘")
        if any(token in text for token in future_tokens) and any(token in text for token in action_tokens):
            title = _compact_text(text, 60)
            detail = _compact_text(f"远提到：{text}", 120)
            self._add_or_update_open_thread(title, detail)
            self._add_proactive_cue_if_missing(title)
            changed = True
        elif "别忘" in text or "记得提醒" in text:
            cue = _compact_text(text, 80)
            self._add_proactive_cue_if_missing(cue)
            changed = True

        if "碎片" in text or "先不展开" in text:
            self.fragmented_chat = True
            changed = True

        if changed:
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
        if self.initiative_events:
            lines.append("recent_initiative_events:")
            for event in self.initiative_events[-3:]:
                lines.append(f"- {event.category}: {event.seed}")
        if self.recent_presence_murmurs:
            recent_murmurs = " / ".join(self.recent_presence_murmurs[-6:])
            lines.append(
                "recent_presence_murmurs_do_not_repeat_exactly: " + recent_murmurs
            )

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
        self.proactive_count_date = _date_key()
        self.relationship_summary = ""
        self.emotional_summary = ""
        self.user_style_summary = ""
        self.open_threads.clear()
        self.initiative_events.clear()
        self.proactive_cues.clear()
        self.recent_topics.clear()
        self.user_returned_recently = False
        self.comfort_needed = False
        self.task_focus = ""
        self.fragmented_chat = False
        self.presence_murmur_count = 0
        self.presence_murmur_count_date = _date_key()
        self.last_presence_murmur_at = 0.0
        self.recent_presence_murmurs.clear()
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
            "proactive_count_date": self.proactive_count_date,
            "relationship_summary": self.relationship_summary,
            "emotional_summary": self.emotional_summary,
            "user_style_summary": self.user_style_summary,
            "open_threads": [thread.to_dict() for thread in self.open_threads],
            "initiative_events": [event.to_dict() for event in self.initiative_events],
            "proactive_cues": self.proactive_cues,
            "recent_topics": self.recent_topics,
            "user_returned_recently": self.user_returned_recently,
            "comfort_needed": self.comfort_needed,
            "task_focus": self.task_focus,
            "fragmented_chat": self.fragmented_chat,
            "presence_murmur_count": self.presence_murmur_count,
            "presence_murmur_count_date": self.presence_murmur_count_date,
            "last_presence_murmur_at": self.last_presence_murmur_at,
            "recent_presence_murmurs": self.recent_presence_murmurs,
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
        self.proactive_count_date = str(data.get("proactive_count_date", "")) or _date_key()
        self.relationship_summary = str(data.get("relationship_summary", ""))
        self.emotional_summary = str(data.get("emotional_summary", ""))
        self.user_style_summary = str(data.get("user_style_summary", ""))
        self.open_threads = [
            OpenThread.from_dict(item)
            for item in data.get("open_threads", [])
            if isinstance(item, dict)
        ]
        self.initiative_events = [
            InitiativeEventRecord.from_dict(item)
            for item in data.get("initiative_events", [])
            if isinstance(item, dict)
        ]
        self.proactive_cues = _string_list(data.get("proactive_cues", []))
        self.recent_topics = _string_list(data.get("recent_topics", []))
        self.user_returned_recently = bool(data.get("user_returned_recently", False))
        self.comfort_needed = bool(data.get("comfort_needed", False))
        self.task_focus = str(data.get("task_focus", ""))
        self.fragmented_chat = bool(data.get("fragmented_chat", False))
        self.presence_murmur_count = int(data.get("presence_murmur_count", 0))
        self.presence_murmur_count_date = (
            str(data.get("presence_murmur_count_date", "")) or _date_key()
        )
        self.last_presence_murmur_at = float(data.get("last_presence_murmur_at", 0.0))
        self.recent_presence_murmurs = [
            _normalize_presence_murmur(item)
            for item in _string_list(data.get("recent_presence_murmurs", []))
            if _normalize_presence_murmur(item)
        ]
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
        self.initiative_events = self.initiative_events[-DEFAULT_MAX_RECENT_TOPICS:]
        self.recent_topics = self.recent_topics[-DEFAULT_MAX_RECENT_TOPICS:]
        self.proactive_cues = self.proactive_cues[-DEFAULT_MAX_RECENT_TOPICS:]
        self.recent_presence_murmurs = self.recent_presence_murmurs[
            -DEFAULT_MAX_RECENT_PRESENCE_MURMURS:
        ]

    def _add_or_update_open_thread(self, title: str, detail: str = "") -> None:
        clean_title = title.strip()
        if not clean_title:
            return
        now = time.time()
        for thread in self.open_threads:
            if thread.title == clean_title:
                thread.detail = detail.strip() or thread.detail
                thread.status = "open"
                thread.updated_at = now
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

    def _add_proactive_cue_if_missing(self, cue: str) -> None:
        clean_cue = cue.strip()
        if clean_cue and clean_cue not in self.proactive_cues:
            self.proactive_cues.append(clean_cue)
            self.proactive_cues = self.proactive_cues[-DEFAULT_MAX_RECENT_TOPICS:]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _date_key(timestamp: Optional[float] = None) -> str:
    moment = datetime.fromtimestamp(timestamp if timestamp is not None else time.time())
    return moment.date().isoformat()


def _compact_text(text: str, limit: int) -> str:
    compacted = " ".join(text.strip().split())
    return compacted[:limit]


def _normalize_presence_murmur(text: object) -> str:
    return " ".join(str(text).strip().split())
