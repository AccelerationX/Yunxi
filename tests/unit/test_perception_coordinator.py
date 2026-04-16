"""PerceptionCoordinator 单元测试。"""

import time

from domains.perception.coordinator import (
    LayeredPerceptionProvider,
    PerceptionLayer,
    PerceptionCoordinator,
    PerceptionSnapshot,
    SystemState,
    TimeContext,
    UserPresence,
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
