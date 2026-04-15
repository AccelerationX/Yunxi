"""感知协调器。

负责聚合时间、用户在场状态、系统状态、外部信息感知数据，
并检测显著变化生成感知事件。
"""

from __future__ import annotations

import ctypes
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol


logger = logging.getLogger(__name__)


@dataclass
class TimeContext:
    readable_time: str = ""
    hour: int = 0


@dataclass
class UserPresence:
    focused_application: str = ""
    idle_duration: float = 0.0
    is_at_keyboard: bool = True


@dataclass
class SystemState:
    cpu_percent: float = 0.0


@dataclass
class ExternalInfo:
    weather: str = ""


@dataclass
class PerceptionSnapshot:
    time_context: TimeContext = field(default_factory=TimeContext)
    user_presence: UserPresence = field(default_factory=UserPresence)
    system_state: SystemState = field(default_factory=SystemState)
    external_info: ExternalInfo = field(default_factory=ExternalInfo)


@dataclass
class PerceptionEvent:
    event_type: str
    description: str
    data: Dict[str, Any] = field(default_factory=dict)


class PerceptionProvider(Protocol):
    """真实感知数据提供者接口。"""

    def fetch(self) -> PerceptionSnapshot:
        """采集当前感知快照。"""


class WindowsPerceptionProvider:
    """基于 Windows 桌面环境的默认感知提供者。"""

    def fetch(self) -> PerceptionSnapshot:
        """采集当前时间、前台窗口、idle 时长和基础系统状态。"""
        now = datetime.now()
        idle_seconds = self._idle_duration_seconds()
        return PerceptionSnapshot(
            time_context=TimeContext(
                readable_time=now.strftime("%Y-%m-%d %H:%M:%S"),
                hour=now.hour,
            ),
            user_presence=UserPresence(
                focused_application=self._focused_application(),
                idle_duration=idle_seconds,
                is_at_keyboard=idle_seconds < 60.0,
            ),
            system_state=SystemState(cpu_percent=self._cpu_percent()),
            external_info=ExternalInfo(),
        )

    def _focused_application(self) -> str:
        """读取当前前台窗口标题。"""
        try:
            import uiautomation as auto

            control = auto.GetForegroundControl()
            if control is None:
                return ""
            name = getattr(control, "Name", "") or ""
            class_name = getattr(control, "ClassName", "") or ""
            if name and class_name:
                return f"{name} ({class_name})"
            return name or class_name
        except Exception as exc:
            logger.debug("Failed to read focused application: %s", exc)
            return ""

    def _idle_duration_seconds(self) -> float:
        """读取用户最近一次键鼠输入距今的秒数。"""

        class LastInputInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint),
                ("dwTime", ctypes.c_uint),
            ]

        info = LastInputInfo()
        info.cbSize = ctypes.sizeof(LastInputInfo)
        try:
            if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
                return 0.0
            tick_count = ctypes.windll.kernel32.GetTickCount64()
            return max(0.0, float(tick_count - info.dwTime) / 1000.0)
        except AttributeError:
            return 0.0
        except OSError as exc:
            logger.debug("Failed to read idle duration: %s", exc)
            return 0.0

    def _cpu_percent(self) -> float:
        """读取系统 CPU 占用率。"""
        try:
            import psutil

            return float(psutil.cpu_percent(interval=None))
        except ImportError:
            logger.debug("psutil is not installed; cpu_percent falls back to 0")
            return 0.0
        except OSError as exc:
            logger.debug("Failed to read cpu percent: %s", exc)
            return 0.0


class PerceptionCoordinator:
    """感知协调器。

    聚合桌面/系统感知数据，检测状态变化并生成事件。
    """

    def __init__(self, provider: Optional[PerceptionProvider] = None) -> None:
        self._current_snapshot = PerceptionSnapshot()
        self._previous_snapshot: Optional[PerceptionSnapshot] = None
        self._injected_snapshot_pending = False
        self._provider = provider or WindowsPerceptionProvider()

    def get_snapshot(self) -> PerceptionSnapshot:
        """返回当前感知快照。"""
        return self._current_snapshot

    def inject_snapshot(self, snapshot: PerceptionSnapshot) -> None:
        """直接注入感知快照（测试用）。"""
        self._previous_snapshot = self._current_snapshot
        self._current_snapshot = snapshot
        self._injected_snapshot_pending = True

    def update(self) -> List[PerceptionEvent]:
        """刷新感知数据并返回检测到的事件列表。"""
        if self._injected_snapshot_pending:
            self._injected_snapshot_pending = False
            return self._compute_events(
                self._previous_snapshot, self._current_snapshot
            )

        self._previous_snapshot = self._current_snapshot
        self._current_snapshot = self._fetch_snapshot()
        return self._compute_events(
            self._previous_snapshot, self._current_snapshot
        )

    def _fetch_snapshot(self) -> PerceptionSnapshot:
        """采集当前真实感知数据。"""
        return self._provider.fetch()

    def _compute_events(
        self,
        old: Optional[PerceptionSnapshot],
        new: PerceptionSnapshot,
    ) -> List[PerceptionEvent]:
        """对比新旧快照，生成感知事件。"""
        events: List[PerceptionEvent] = []
        if old is None:
            return events

        old_app = getattr(old.user_presence, "focused_application", "")
        new_app = getattr(new.user_presence, "focused_application", "")
        if old_app != new_app and new_app:
            events.append(
                PerceptionEvent(
                    event_type="app_changed",
                    description=f"用户切换到 {new_app}",
                    data={"from": old_app, "to": new_app},
                )
            )

        old_idle = getattr(old.user_presence, "idle_duration", 0.0)
        new_idle = getattr(new.user_presence, "idle_duration", 0.0)
        if old_idle < 300 and new_idle >= 300:
            events.append(
                PerceptionEvent(
                    event_type="long_idle",
                    description="用户已经离开超过 5 分钟",
                    data={"idle_duration": new_idle},
                )
            )
        if old_idle >= 300 and new_idle < 30:
            events.append(
                PerceptionEvent(
                    event_type="user_returned",
                    description="用户回来了",
                    data={"idle_duration": new_idle},
                )
            )

        new_hour = getattr(new.time_context, "hour", 0)
        if 22 <= new_hour or new_hour < 6:
            events.append(
                PerceptionEvent(
                    event_type="late_night",
                    description="已经是深夜了",
                    data={"hour": new_hour},
                )
            )

        return events
