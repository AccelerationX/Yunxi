"""Tests for Feishu WebSocket lifecycle behavior."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from interfaces.feishu.websocket import FeishuWebSocket


class StoppableClient:
    def __init__(self, *args, **kwargs) -> None:
        self.stopped = threading.Event()

    def start(self) -> None:
        self.stopped.wait(timeout=5)

    def stop(self) -> None:
        self.stopped.set()


def test_feishu_websocket_stop_closes_client_and_joins_thread(monkeypatch):
    created: list[StoppableClient] = []

    def fake_client(*args, **kwargs) -> StoppableClient:
        client = StoppableClient(*args, **kwargs)
        created.append(client)
        return client

    monkeypatch.setattr("interfaces.feishu.websocket.lark.ws.Client", fake_client)

    websocket = FeishuWebSocket(
        app_id="app-id",
        app_secret="app-secret",
        startup_wait_seconds=0,
    )

    assert websocket.start()
    assert created
    assert websocket._thread is not None
    assert websocket._thread.is_alive()

    websocket.stop(join_timeout=1)

    assert created[0].stopped.is_set()
    assert websocket._thread is None


def test_feishu_websocket_deduplicates_messages():
    received: list[tuple[str, str, str]] = []
    websocket = FeishuWebSocket(
        app_id="app-id",
        app_secret="app-secret",
        on_message=lambda user_id, chat_id, content: received.append(
            (user_id, chat_id, content)
        ),
    )
    message = _message_event(message_id="msg-1", sender_id="user-1", text="你好")

    websocket._handle_message(message)
    websocket._handle_message(message)

    assert received == [("user-1", "chat-1", "你好")]


def test_feishu_websocket_filters_ignored_sender():
    received: list[tuple[str, str, str]] = []
    websocket = FeishuWebSocket(
        app_id="app-id",
        app_secret="app-secret",
        ignored_sender_ids={"bot-open-id"},
        on_message=lambda user_id, chat_id, content: received.append(
            (user_id, chat_id, content)
        ),
    )

    websocket._handle_message(
        _message_event(message_id="msg-1", sender_id="bot-open-id", text="自发消息")
    )

    assert received == []


def test_feishu_websocket_prunes_old_dedupe_entries():
    websocket = FeishuWebSocket(
        app_id="app-id",
        app_secret="app-secret",
        dedupe_ttl_seconds=1,
        max_processed_messages=2,
    )

    assert websocket._mark_message_processed("old")
    websocket._processed_messages["old"] = time.time() - 10
    assert websocket._mark_message_processed("new")

    assert list(websocket._processed_messages) == ["new"]


def _message_event(message_id: str, sender_id: str, text: str):
    message = SimpleNamespace(
        message_id=message_id,
        chat_id="chat-1",
        create_time=str(int(time.time() * 1000)),
        message_type="text",
        content=f'{{"text": "{text}"}}',
    )
    sender = SimpleNamespace(
        sender_id=SimpleNamespace(open_id=sender_id),
    )
    event = SimpleNamespace(message=message, sender=sender)
    return SimpleNamespace(event=event)
