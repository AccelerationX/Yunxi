"""Tests for Feishu adapter async/thread bridging."""

from __future__ import annotations

import asyncio
import threading

import pytest

from interfaces.feishu.adapter import FeishuAdapter


class FakeRuntime:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def chat(self, content: str) -> str:
        self.messages.append(content)
        await asyncio.sleep(0.01)
        return f"云汐回复：{content}"


class FakeFeishuClient:
    def __init__(self) -> None:
        self.sent_texts: list[dict[str, str]] = []
        self.proactive_texts: list[str] = []

    def send_text(
        self,
        content: str,
        receive_id: str | None = None,
        receive_id_type: str = "open_id",
    ) -> dict[str, object]:
        self.sent_texts.append(
            {
                "content": content,
                "receive_id": receive_id or "",
                "receive_id_type": receive_id_type,
            }
        )
        return {"code": 0}

    def send_text_to_user(
        self,
        content: str,
        user_id: str | None = None,
    ) -> dict[str, object]:
        self.proactive_texts.append(content)
        return {"code": 0}


@pytest.mark.asyncio
async def test_feishu_message_callback_from_thread_enters_main_loop():
    runtime = FakeRuntime()
    client = FakeFeishuClient()
    adapter = FeishuAdapter(
        runtime=runtime,
        feishu_client=client,
        event_loop=asyncio.get_running_loop(),
    )
    futures = []

    def worker() -> None:
        futures.append(adapter.on_feishu_message("user-1", "chat-1", "你好"))

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=1)

    assert futures
    await asyncio.wait_for(asyncio.wrap_future(futures[0]), timeout=1)
    assert runtime.messages == ["你好"]
    assert client.sent_texts == [
        {
            "content": "云汐回复：你好",
            "receive_id": "chat-1",
            "receive_id_type": "chat_id",
        }
    ]


@pytest.mark.asyncio
async def test_feishu_message_callback_from_loop_uses_task():
    runtime = FakeRuntime()
    client = FakeFeishuClient()
    adapter = FeishuAdapter(
        runtime=runtime,
        feishu_client=client,
        event_loop=asyncio.get_running_loop(),
    )

    task = adapter.on_feishu_message("user-1", "chat-1", "在吗")

    assert isinstance(task, asyncio.Task)
    await asyncio.wait_for(task, timeout=1)
    assert runtime.messages == ["在吗"]
    assert client.sent_texts[0]["content"] == "云汐回复：在吗"


@pytest.mark.asyncio
async def test_feishu_proactive_send_uses_async_path():
    runtime = FakeRuntime()
    client = FakeFeishuClient()
    adapter = FeishuAdapter(
        runtime=runtime,
        feishu_client=client,
        event_loop=asyncio.get_running_loop(),
    )

    await adapter.send_proactive_message("远，我在。")

    assert client.proactive_texts == ["远，我在。"]
