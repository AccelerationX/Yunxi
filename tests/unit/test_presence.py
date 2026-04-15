"""YunxiPresence 单元测试。"""

import pytest

from core.resident.presence import YunxiPresence


@pytest.mark.asyncio
async def test_presence_run_once_emits_proactive_message():
    emitted = []

    async def proactive_tick():
        return "远～"

    async def on_message(message: str):
        emitted.append(message)

    presence = YunxiPresence(
        proactive_tick=proactive_tick,
        on_proactive_message=on_message,
        tick_interval=0.01,
    )

    message = await presence.run_once()

    assert message == "远～"
    assert emitted == ["远～"]


@pytest.mark.asyncio
async def test_presence_run_once_ignores_empty_message():
    emitted = []

    async def proactive_tick():
        return None

    def on_message(message: str):
        emitted.append(message)

    presence = YunxiPresence(
        proactive_tick=proactive_tick,
        on_proactive_message=on_message,
    )

    message = await presence.run_once()

    assert message is None
    assert emitted == []
