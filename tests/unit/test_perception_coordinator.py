"""PerceptionCoordinator 单元测试。"""

import time

from domains.perception.coordinator import (
    classify_activity_state,
    LayeredPerceptionProvider,
    PerceptionLayer,
    PerceptionCoordinator,
    PerceptionSnapshot,
    SystemState,
    TimeContext,
    UserPresence,
    WindowsUserPresenceProvider,
)


class StaticPerceptionProvider:
    """测试用固定感知提供者。"""

    def __init__(self, snapshot: PerceptionSnapshot):
        self.snapshot = snapshot

    def fetch(self) -> PerceptionSnapshot:
        """返回固定快照。"""
        return self.snapshot


def test_injected_snapshot_survives_next_update():
    coordinator = PerceptionCoordinator()
    snapshot = PerceptionSnapshot(
        time_context=TimeContext(readable_time="2026-04-15 10:00", hour=10),
        user_presence=UserPresence(focused_application="VS Code", idle_duration=0),
    )

    coordinator.inject_snapshot(snapshot)
    events = coordinator.update()
    current = coordinator.get_snapshot()

    assert current.user_presence.focused_application == "VS Code"
    assert any(e.event_type == "app_changed" for e in events)


def test_injected_snapshot_is_one_shot():
    provider = StaticPerceptionProvider(
        PerceptionSnapshot(
            user_presence=UserPresence(focused_application="", idle_duration=0)
        )
    )
    coordinator = PerceptionCoordinator(provider=provider)
    snapshot = PerceptionSnapshot(
        user_presence=UserPresence(focused_application="VS Code", idle_duration=0)
    )

    coordinator.inject_snapshot(snapshot)
    coordinator.update()
    coordinator.update()

    assert coordinator.get_snapshot().user_presence.focused_application == ""


def test_provider_snapshot_is_used_after_injection_window():
    provider = StaticPerceptionProvider(
        PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-15 11:00", hour=11),
            user_presence=UserPresence(
                focused_application="真实前台窗口",
                idle_duration=12,
                is_at_keyboard=True,
            ),
        )
    )
    coordinator = PerceptionCoordinator(provider=provider)

    coordinator.update()

    snapshot = coordinator.get_snapshot()
    assert snapshot.time_context.hour == 11
    assert snapshot.user_presence.focused_application == "真实前台窗口"
    assert snapshot.user_presence.idle_duration == 12


def test_perception_events_include_activity_fullscreen_and_input_changes():
    coordinator = PerceptionCoordinator()
    old_snapshot = PerceptionSnapshot(
        user_presence=UserPresence(
            focused_application="VS Code",
            foreground_process_name="Code.exe",
            idle_duration=0,
            input_events_per_minute=5,
        )
    )
    new_snapshot = PerceptionSnapshot(
        user_presence=UserPresence(
            focused_application="Steam Game",
            foreground_process_name="eldenring.exe",
            idle_duration=0,
            is_fullscreen=True,
            input_events_per_minute=45,
        )
    )

    coordinator.inject_snapshot(old_snapshot)
    coordinator.update()
    coordinator.inject_snapshot(new_snapshot)
    events = coordinator.update()
    event_types = {event.event_type for event in events}

    assert "app_changed" in event_types
    assert "activity_state_changed" in event_types
    assert "fullscreen_started" in event_types
    assert "high_input_activity" in event_types


def test_user_presence_classifies_activity_state():
    assert UserPresence(focused_application="Visual Studio Code", idle_duration=0).activity_state == "work"
    assert UserPresence(foreground_process_name="Code.exe", idle_duration=0).activity_state == "work"
    assert UserPresence(focused_application="Steam Game", idle_duration=0).activity_state == "game"
    assert UserPresence(foreground_process_name="YuanShen.exe", is_fullscreen=True).activity_state == "game"
    assert UserPresence(focused_application="YouTube - Chrome", idle_duration=0).activity_state == "leisure"
    assert UserPresence(
        focused_application="Unknown Window",
        foreground_process_name="unknown.exe",
        is_fullscreen=True,
    ).activity_state == "game"
    assert UserPresence(focused_application="VS Code", idle_duration=360).activity_state == "idle"
    assert classify_activity_state("", idle_duration=1200, is_at_keyboard=False) == "away"


def test_user_presence_keeps_richer_desktop_signals():
    presence = UserPresence(
        focused_application="Bilibili - Chrome",
        foreground_process_name="chrome.exe",
        foreground_window_class="Chrome_WidgetWin_1",
        idle_duration=3,
        is_fullscreen=True,
        input_events_per_minute=12,
    )

    assert presence.foreground_process_name == "chrome.exe"
    assert presence.foreground_window_class == "Chrome_WidgetWin_1"
    assert presence.is_fullscreen is True
    assert presence.input_events_per_minute == 12
    assert presence.activity_state == "leisure"


def test_windows_presence_provider_estimates_input_frequency():
    provider = WindowsUserPresenceProvider()

    first = provider._input_events_per_minute(0.1)
    second = provider._input_events_per_minute(10.0)
    provider._previous_idle_seconds = 10.0
    third = provider._input_events_per_minute(0.1)

    assert first == 1.0
    assert second == 1.0
    assert third >= 2.0


class SlowPerceptionProvider:
    """A provider that should be degraded by timeout."""

    def fetch(self) -> PerceptionSnapshot:
        time.sleep(0.2)
        return PerceptionSnapshot(
            user_presence=UserPresence(focused_application="慢速窗口")
        )


def test_layered_provider_degrades_slow_optional_layer():
    provider = LayeredPerceptionProvider(
        layers=[
            PerceptionLayer(
                name="fast",
                provider=StaticPerceptionProvider(
                    PerceptionSnapshot(
                        time_context=TimeContext(
                            readable_time="2026-04-16 12:00",
                            hour=12,
                        )
                    )
                ),
                timeout_seconds=0.05,
                optional=False,
            ),
            PerceptionLayer(
                name="slow",
                provider=SlowPerceptionProvider(),
                timeout_seconds=0.01,
                optional=True,
            ),
            PerceptionLayer(
                name="system",
                provider=StaticPerceptionProvider(
                    PerceptionSnapshot(system_state=SystemState(cpu_percent=12.5))
                ),
                timeout_seconds=0.05,
                optional=True,
            ),
        ]
    )

    snapshot = provider.fetch()
    provider.close()

    assert snapshot.time_context.hour == 12
    assert snapshot.system_state.cpu_percent == 12.5
    assert snapshot.user_presence.focused_application == ""
    assert provider.last_failures == {"slow": "timeout"}
