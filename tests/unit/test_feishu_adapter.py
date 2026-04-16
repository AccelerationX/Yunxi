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


class PendingRuntime:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def chat(self, content: str) -> str:
        self.messages.append(content)
        if content == "确认":
            return "好，我已经按你点头的那一步处理好了。"
        return "这一步会改动你的电脑状态，我想先等你点头。"


class FailingRuntime:
    async def chat(self, content: str) -> str:
        raise RuntimeError("All connection attempts failed")


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


@pytest.mark.asyncio
async def test_feishu_confirmation_message_goes_through_runtime():
    runtime = PendingRuntime()
    client = FakeFeishuClient()
    adapter = FeishuAdapter(
        runtime=runtime,
        feishu_client=client,
        event_loop=asyncio.get_running_loop(),
    )

    await adapter.handle_message("user-1", "chat-1", "帮我写入剪贴板")
    await adapter.handle_message("user-1", "chat-1", "确认")

    assert runtime.messages == ["帮我写入剪贴板", "确认"]
    assert "点头" in client.sent_texts[0]["content"]
    assert "已经按你点头" in client.sent_texts[1]["content"]


@pytest.mark.asyncio
async def test_feishu_runtime_error_reply_hides_technical_detail():
    client = FakeFeishuClient()
    adapter = FeishuAdapter(
        runtime=FailingRuntime(),
        feishu_client=client,
        event_loop=asyncio.get_running_loop(),
    )

    await adapter.handle_message("user-1", "chat-1", "你好")

    reply = client.sent_texts[0]["content"]
    assert "All connection attempts failed" not in reply
    assert "卡了一下" in reply
