"""感知协调器。

负责聚合时间、用户在场状态、系统状态、外部信息感知数据，
并检测显著变化生成感知事件。
"""

from __future__ import annotations

import ctypes
import concurrent.futures
import logging
import time
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
    foreground_process_name: str = ""
    foreground_window_class: str = ""
    idle_duration: float = 0.0
    is_at_keyboard: bool = True
    is_fullscreen: bool = False
    input_events_per_minute: float = 0.0
    activity_state: str = ""

    def __post_init__(self) -> None:
        if not self.activity_state:
            self.activity_state = classify_activity_state(
                self.focused_application,
                self.foreground_process_name,
                self.idle_duration,
                self.is_at_keyboard,
                self.is_fullscreen,
                self.input_events_per_minute,
            )


@dataclass
class SystemState:
    cpu_percent: float = 0.0


@dataclass
class ExternalInfo:
    weather: str = ""


@dataclass(frozen=True)
class ForegroundWindowInfo:
    """Foreground window details collected from the OS."""

    title: str = ""
    class_name: str = ""
    process_name: str = ""
    is_fullscreen: bool = False


def classify_activity_state(
    focused_application: str = "",
    foreground_process_name: str = "",
    idle_duration: float = 0.0,
    is_at_keyboard: bool = True,
    is_fullscreen: bool = False,
    input_events_per_minute: float = 0.0,
) -> str:
    """Classify the user's coarse computer-usage state for interruption cost."""
    app = f"{focused_application or ''} {foreground_process_name or ''}".lower()
    process = (foreground_process_name or "").lower()
    idle = float(idle_duration or 0.0)
    if idle >= 900 or not is_at_keyboard and idle >= 300:
        return "away"
    if idle >= 300:
        return "idle"

    work_tokens = (
        "code", "visual studio", "pycharm", "idea", "webstorm", "terminal",
        "powershell", "cmd", "windows terminal", "notepad++", "word", "excel",
        "powerpoint", "wps", "obsidian", "typora", "photoshop", "premiere",
        "blender", "unity", "unreal", "figma",
    )
    game_tokens = (
        "steam", "epic games", "valorant", "league of legends", "genshin",
        "yuanshen", "starrail", "zenless", "eldenring", "palworld", "cs2",
        "dota2", "lol", "pubg", "原神", "崩坏", "英雄联盟", "绝地求生",
        "minecraft", "game",
    )
    leisure_tokens = (
        "youtube", "bilibili", "哔哩", "netflix", "spotify", "music",
        "qq音乐", "网易云音乐", "vlc", "potplayer", "chrome", "edge",
        "firefox", "browser", "浏览器",
    )
    video_processes = ("vlc", "potplayer", "mpv", "chrome", "edge", "firefox")
    work_processes = (
        "code.exe", "pycharm", "idea", "webstorm", "devenv.exe", "windowsterminal",
        "powershell", "cmd.exe", "winword", "excel", "powerpnt", "obsidian",
        "typora", "photoshop", "premiere", "blender", "figma",
    )

    if any(token in app for token in game_tokens):
        return "game"
    if is_fullscreen and process and not any(token in process for token in video_processes):
        if not any(token in process for token in work_processes):
            return "game"
    if any(token in app for token in work_tokens):
        return "work"
    if any(token in app for token in leisure_tokens):
        return "leisure"
    if input_events_per_minute >= 45 and is_fullscreen:
        return "game"
    if app:
        return "unknown"
    return "unknown"


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


class TimePerceptionProvider:
    """Fast local time perception."""

    def fetch(self) -> PerceptionSnapshot:
        """Collect current local time."""
        now = datetime.now()
        return PerceptionSnapshot(
            time_context=TimeContext(
                readable_time=now.strftime("%Y-%m-%d %H:%M:%S"),
                hour=now.hour,
            )
        )


class WindowsUserPresenceProvider:
    """Windows foreground-window and idle perception."""

    def __init__(self) -> None:
        self._previous_idle_seconds: Optional[float] = None
        self._last_inferred_input_at: float = 0.0
        self._input_event_times: List[float] = []

    def fetch(self) -> PerceptionSnapshot:
        """Collect foreground app and keyboard-idle state."""
        idle_seconds = self._idle_duration_seconds()
        foreground = self._foreground_window_info()
        input_events_per_minute = self._input_events_per_minute(idle_seconds)
        return PerceptionSnapshot(
            user_presence=UserPresence(
                focused_application=foreground.title,
                foreground_process_name=foreground.process_name,
                foreground_window_class=foreground.class_name,
                idle_duration=idle_seconds,
                is_at_keyboard=idle_seconds < 60.0,
                is_fullscreen=foreground.is_fullscreen,
                input_events_per_minute=input_events_per_minute,
            ),
        )

    def _focused_application(self) -> str:
        """读取当前前台窗口标题。"""
        info = self._foreground_window_info()
        if info.title:
            return info.title
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

    def _foreground_window_info(self) -> "ForegroundWindowInfo":
        """Read foreground title, class, process name, and fullscreen state."""
        if not hasattr(ctypes, "windll"):
            return ForegroundWindowInfo()
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return ForegroundWindowInfo()

            title_length = user32.GetWindowTextLengthW(hwnd)
            title_buffer = ctypes.create_unicode_buffer(title_length + 1)
            user32.GetWindowTextW(hwnd, title_buffer, title_length + 1)

            class_buffer = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_buffer, 256)

            process_id = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            process_name = self._process_name(int(process_id.value))
            is_fullscreen = self._is_fullscreen_window(hwnd)
            return ForegroundWindowInfo(
                title=_format_focused_application(title_buffer.value, class_buffer.value),
                class_name=class_buffer.value,
                process_name=process_name,
                is_fullscreen=is_fullscreen,
            )
        except (AttributeError, OSError) as exc:
            logger.debug("Failed to read foreground window info: %s", exc)
            return ForegroundWindowInfo()

    def _process_name(self, process_id: int) -> str:
        if process_id <= 0:
            return ""
        try:
            import psutil

            return str(psutil.Process(process_id).name() or "")
        except ImportError:
            return ""
        except (OSError, psutil.Error) as exc:
            logger.debug("Failed to read foreground process name: %s", exc)
            return ""

    def _is_fullscreen_window(self, hwnd: int) -> bool:
        if not hasattr(ctypes, "windll"):
            return False

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", ctypes.c_ulong),
            ]

        try:
            user32 = ctypes.windll.user32
            rect = RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return False
            monitor = user32.MonitorFromWindow(hwnd, 2)
            monitor_info = MONITORINFO()
            monitor_info.cbSize = ctypes.sizeof(MONITORINFO)
            if not user32.GetMonitorInfoW(monitor, ctypes.byref(monitor_info)):
                return False
            monitor_rect = monitor_info.rcMonitor
            tolerance = 2
            return (
                rect.left <= monitor_rect.left + tolerance
                and rect.top <= monitor_rect.top + tolerance
                and rect.right >= monitor_rect.right - tolerance
                and rect.bottom >= monitor_rect.bottom - tolerance
            )
        except (AttributeError, OSError) as exc:
            logger.debug("Failed to read fullscreen state: %s", exc)
            return False

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

    def _input_events_per_minute(self, idle_seconds: float) -> float:
        """Estimate recent input frequency without installing a global hook."""
        now = time.time()
        previous = self._previous_idle_seconds
        inferred_new_input = False
        if idle_seconds < 2.0:
            if previous is None or idle_seconds + 0.5 < previous:
                inferred_new_input = True
            elif now - self._last_inferred_input_at >= 2.0:
                inferred_new_input = True
        if inferred_new_input:
            self._input_event_times.append(now)
            self._last_inferred_input_at = now
        self._previous_idle_seconds = idle_seconds
        cutoff = now - 60.0
        self._input_event_times = [
            event_time for event_time in self._input_event_times if event_time >= cutoff
        ]
        return float(len(self._input_event_times))


class SystemResourceProvider:
    """Fast local system resource perception."""

    def fetch(self) -> PerceptionSnapshot:
        """Collect basic system state."""
        return PerceptionSnapshot(system_state=SystemState(cpu_percent=self._cpu_percent()))

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


class WindowsPerceptionProvider:
    """Backward-compatible one-shot Windows perception provider."""

    def __init__(self) -> None:
        self._time = TimePerceptionProvider()
        self._presence = WindowsUserPresenceProvider()
        self._system = SystemResourceProvider()

    def fetch(self) -> PerceptionSnapshot:
        """采集当前时间、前台窗口、idle 时长和基础系统状态。"""
        return merge_snapshots(
            self._time.fetch(),
            self._presence.fetch(),
            self._system.fetch(),
        )


@dataclass(frozen=True)
class PerceptionLayer:
    """One perception provider layer with an independent timeout."""

    name: str
    provider: PerceptionProvider
    timeout_seconds: float = 0.5
    optional: bool = True


class LayeredPerceptionProvider:
    """Run perception providers by layer with timeout and degradation."""

    def __init__(
        self,
        layers: Optional[List[PerceptionLayer]] = None,
        fallback: Optional[PerceptionSnapshot] = None,
    ) -> None:
        self.layers = layers or [
            PerceptionLayer(
                name="basic_time",
                provider=TimePerceptionProvider(),
                timeout_seconds=0.2,
                optional=False,
            ),
            PerceptionLayer(
                name="desktop_presence",
                provider=WindowsUserPresenceProvider(),
                timeout_seconds=1.0,
                optional=True,
            ),
            PerceptionLayer(
                name="system_resource",
                provider=SystemResourceProvider(),
                timeout_seconds=0.5,
                optional=True,
            ),
        ]
        self.fallback = fallback or PerceptionSnapshot()
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, len(self.layers)),
            thread_name_prefix="yunxi-perception",
        )
        self.last_failures: Dict[str, str] = {}

    def fetch(self) -> PerceptionSnapshot:
        """Collect a merged snapshot while degrading slow or failed layers."""
        snapshots: List[PerceptionSnapshot] = []
        failures: Dict[str, str] = {}

        for layer in self.layers:
            future = self._executor.submit(layer.provider.fetch)
            try:
                snapshots.append(future.result(timeout=layer.timeout_seconds))
            except concurrent.futures.TimeoutError:
                failures[layer.name] = "timeout"
                future.cancel()
                if not layer.optional:
                    logger.warning("Required perception layer timed out: %s", layer.name)
            except Exception as exc:
                failures[layer.name] = exc.__class__.__name__
                logger.debug("Perception layer failed: %s: %s", layer.name, exc)
                if not layer.optional:
                    logger.warning("Required perception layer failed: %s", layer.name)

        self.last_failures = failures
        if not snapshots:
            return self.fallback
        return merge_snapshots(*snapshots)

    def close(self) -> None:
        """Stop perception worker threads without waiting on stuck providers."""
        self._executor.shutdown(wait=False, cancel_futures=True)


def merge_snapshots(*snapshots: PerceptionSnapshot) -> PerceptionSnapshot:
    """Merge partial perception snapshots into one complete snapshot."""
    merged = PerceptionSnapshot()
    for snapshot in snapshots:
        if snapshot.time_context.readable_time or snapshot.time_context.hour:
            merged.time_context = snapshot.time_context
        if (
            snapshot.user_presence.focused_application
            or snapshot.user_presence.foreground_process_name
            or snapshot.user_presence.foreground_window_class
            or snapshot.user_presence.idle_duration
            or not snapshot.user_presence.is_at_keyboard
            or snapshot.user_presence.is_fullscreen
            or snapshot.user_presence.input_events_per_minute
        ):
            merged.user_presence = snapshot.user_presence
        if snapshot.system_state.cpu_percent:
            merged.system_state = snapshot.system_state
        if snapshot.external_info.weather:
            merged.external_info = snapshot.external_info
    return merged


class PerceptionCoordinator:
    """感知协调器。

    聚合桌面/系统感知数据，检测状态变化并生成事件。
    """

    def __init__(self, provider: Optional[PerceptionProvider] = None) -> None:
        self._current_snapshot = PerceptionSnapshot()
        self._previous_snapshot: Optional[PerceptionSnapshot] = None
        self._injected_snapshot_pending = False
        self._provider = provider or LayeredPerceptionProvider()

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

    def close(self) -> None:
        """Release provider resources when supported."""
        close = getattr(self._provider, "close", None)
        if callable(close):
            close()

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
                    data={
                        "from": old_app,
                        "to": new_app,
                        "process": getattr(new.user_presence, "foreground_process_name", ""),
                    },
                )
            )

        old_activity = getattr(old.user_presence, "activity_state", "")
        new_activity = getattr(new.user_presence, "activity_state", "")
        if old_activity != new_activity and new_activity:
            events.append(
                PerceptionEvent(
                    event_type="activity_state_changed",
                    description=f"用户电脑使用状态变为 {new_activity}",
                    data={"from": old_activity, "to": new_activity},
                )
            )

        old_fullscreen = bool(getattr(old.user_presence, "is_fullscreen", False))
        new_fullscreen = bool(getattr(new.user_presence, "is_fullscreen", False))
        if not old_fullscreen and new_fullscreen:
            events.append(
                PerceptionEvent(
                    event_type="fullscreen_started",
                    description="前台窗口进入全屏",
                    data={
                        "application": new_app,
                        "process": getattr(new.user_presence, "foreground_process_name", ""),
                    },
                )
            )
        elif old_fullscreen and not new_fullscreen:
            events.append(
                PerceptionEvent(
                    event_type="fullscreen_ended",
                    description="前台窗口退出全屏",
                    data={
                        "application": new_app,
                        "process": getattr(new.user_presence, "foreground_process_name", ""),
                    },
                )
            )

        old_input_rate = float(
            getattr(old.user_presence, "input_events_per_minute", 0.0) or 0.0
        )
        new_input_rate = float(
            getattr(new.user_presence, "input_events_per_minute", 0.0) or 0.0
        )
        if old_input_rate < 30 <= new_input_rate:
            events.append(
                PerceptionEvent(
                    event_type="high_input_activity",
                    description="用户正在频繁输入",
                    data={"input_events_per_minute": new_input_rate},
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


def _format_focused_application(title: str, class_name: str = "") -> str:
    title = (title or "").strip()
    class_name = (class_name or "").strip()
    if title and class_name:
        return f"{title} ({class_name})"
    return title or class_name
