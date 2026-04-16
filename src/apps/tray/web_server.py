"""Tray/WebUI 状态控制面板数据适配。

正式日常对话统一走飞书；这里只暴露状态、日志和本地控制面板所需数据。
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List

from core.runtime import YunxiRuntime


@dataclass
class RuntimeStatus:
    """Runtime 暴露给 Tray/WebUI 状态控制面板的状态快照。"""

    mode: str
    emotion: str
    miss_value: float
    focused_application: str
    available_tools: List[str] = field(default_factory=list)
    continuity_size: int = 0
    unanswered_proactive_count: int = 0

    def to_dict(self) -> Dict[str, object]:
        """转换为 Web JSON 可序列化结构。"""
        return asdict(self)


def build_runtime_status(runtime: YunxiRuntime) -> RuntimeStatus:
    """从 Runtime 构建 Tray/WebUI 状态控制面板快照。"""
    context = runtime.get_context()
    heart_lake = context.heart_lake_state
    perception = context.perception_snapshot
    focused_application = ""
    if perception and perception.user_presence:
        focused_application = perception.user_presence.focused_application

    return RuntimeStatus(
        mode=context.mode,
        emotion=getattr(heart_lake, "current_emotion", "平静"),
        miss_value=float(getattr(heart_lake, "miss_value", 0.0)),
        focused_application=focused_application,
        available_tools=list(context.available_tools),
        continuity_size=len(runtime.continuity.exchanges),
        unanswered_proactive_count=runtime.continuity.unanswered_proactive_count,
    )
