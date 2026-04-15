"""对话连续性服务。"""

from dataclasses import dataclass, field
from typing import List


DEFAULT_MAX_EXCHANGES = 50
DEFAULT_SUMMARY_LIMIT = 20


@dataclass
class ConversationExchange:
    """一轮用户与云汐的对话记录。"""

    user_message: str
    assistant_message: str
    proactive: bool = False


@dataclass
class CompanionContinuityService:
    """维护最近对话窗口和未回复主动消息计数。"""

    max_exchanges: int = DEFAULT_MAX_EXCHANGES
    exchanges: List[ConversationExchange] = field(default_factory=list)
    unanswered_proactive_count: int = 0

    def record_exchange(
        self,
        user_message: str,
        assistant_message: str,
        proactive: bool = False,
    ) -> None:
        """记录一轮完整对话。"""
        self.exchanges.append(
            ConversationExchange(
                user_message=user_message,
                assistant_message=assistant_message,
                proactive=proactive,
            )
        )
        if proactive:
            self.unanswered_proactive_count += 1
        elif user_message:
            self.unanswered_proactive_count = 0
        self._trim()

    def record_assistant_message(self, message: str, proactive: bool = False) -> None:
        """记录没有对应用户输入的 assistant 消息。"""
        self.record_exchange("", message, proactive=proactive)

    def get_recent_exchanges(self, limit: int = DEFAULT_SUMMARY_LIMIT) -> List[ConversationExchange]:
        """返回最近的对话记录。"""
        return self.exchanges[-limit:]

    def get_summary(self, limit: int = DEFAULT_SUMMARY_LIMIT) -> str:
        """生成供 prompt 使用的连续性摘要。"""
        lines: List[str] = []
        for exchange in self.get_recent_exchanges(limit):
            if exchange.user_message:
                lines.append(f"远：{exchange.user_message}")
            label = "云汐（主动）" if exchange.proactive else "云汐"
            if exchange.assistant_message:
                lines.append(f"{label}：{exchange.assistant_message}")
        return "\n".join(lines)

    def reset(self) -> None:
        """清空连续性状态。"""
        self.exchanges.clear()
        self.unanswered_proactive_count = 0

    def _trim(self) -> None:
        if len(self.exchanges) > self.max_exchanges:
            self.exchanges = self.exchanges[-self.max_exchanges :]
