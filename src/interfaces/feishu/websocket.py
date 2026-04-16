"""飞书 WebSocket 客户端。

使用 lark-oapi 库建立长连接，接收飞书消息并回调处理。
从 yunxi-ai/feishu_websocket.py 适配而来。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional

import lark_oapi as lark
import lark_oapi.ws.client as lark_ws_client
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1


logger = logging.getLogger(__name__)


class FeishuWebSocket:
    """飞书 WebSocket 客户端。"""

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        on_message: Optional[Callable[[str, str, str], None]] = None,
        startup_wait_seconds: float = 2.0,
        ignored_sender_ids: Optional[set[str]] = None,
        dedupe_ttl_seconds: float = 300.0,
        max_processed_messages: int = 2000,
        # on_message(user_id, chat_id, content) -> None
    ):
        self.app_id = app_id or os.getenv("FEISHU_APP_ID", "")
        self.app_secret = app_secret or os.getenv("FEISHU_APP_SECRET", "")
        self._on_message = on_message
        self._startup_wait_seconds = max(0.0, startup_wait_seconds)
        self._ignored_sender_ids = ignored_sender_ids or self._load_ignored_sender_ids()
        self._dedupe_ttl_seconds = max(1.0, dedupe_ttl_seconds)
        self._max_processed_messages = max(1, max_processed_messages)
        self._client: Optional[lark.ws.Client] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._processed_messages: OrderedDict[str, float] = OrderedDict()
        self._processed_lock = threading.Lock()

    def _handle_message(self, data: P2ImMessageReceiveV1) -> None:
        """处理收到的飞书消息。"""
        try:
            event = data.event
            message = event.message
            sender = event.sender
            message_id = message.message_id
            sender_id = sender.sender_id.open_id
            chat_id = message.chat_id

            if sender_id in self._ignored_sender_ids:
                logger.debug("忽略飞书自身消息: %s", sender_id)
                return

            if not self._mark_message_processed(message_id):
                return

            # 忽略 5 分钟前的消息
            current_time = int(time.time() * 1000)
            create_time = int(message.create_time)
            if current_time - create_time > 5 * 60 * 1000:
                return

            # 只处理文本消息
            if message.message_type != "text":
                logger.info(f"收到非文本消息: {message.message_type}")
                return

            content = json.loads(message.content).get("text", "").strip()
            if not content:
                return

            logger.info(f"收到飞书消息 from {sender_id}: {content[:50]}...")

            if self._on_message:
                self._on_message(sender_id, chat_id, content)

        except Exception as e:
            logger.exception(f"处理飞书消息异常: {e}")

    def _create_handler(self):
        """创建事件处理器。"""
        def event_handler(data: P2ImMessageReceiveV1) -> None:
            self._handle_message(data)

        return (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(event_handler)
            .build()
        )

    def start(self) -> bool:
        """启动 WebSocket 连接。"""
        if not self.app_id or not self.app_secret:
            logger.error("飞书配置不完整，请检查 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
            return False

        if self._running:
            logger.warning("WebSocket 已在运行中")
            return True

        logger.info("启动飞书 WebSocket 客户端...")

        try:
            event_handler = self._create_handler()
            self._client = lark.ws.Client(
                self.app_id,
                self.app_secret,
                event_handler=event_handler,
                log_level=lark.LogLevel.WARNING,
            )

            def run_ws():
                self._running = True
                try:
                    self._client.start()
                except Exception as e:
                    if self._running:
                        logger.exception(f"WebSocket 异常: {e}")
                    else:
                        logger.info("飞书 WebSocket 线程已退出: %s", e)
                finally:
                    self._running = False

            self._thread = threading.Thread(
                target=run_ws,
                name="yunxi-feishu-websocket",
                daemon=True,
            )
            self._thread.start()

            # 等待连接建立
            if self._startup_wait_seconds:
                time.sleep(self._startup_wait_seconds)
            logger.info("飞书 WebSocket 已启动")
            return True

        except Exception as e:
            logger.exception(f"启动飞书 WebSocket 失败: {e}")
            return False

    def stop(self, join_timeout: float = 5.0) -> None:
        """停止 WebSocket 连接。"""
        self._running = False
        self._stop_client(join_timeout=join_timeout)
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=join_timeout)
            if thread.is_alive():
                logger.warning("飞书 WebSocket 线程未在 %.1f 秒内退出", join_timeout)
        self._thread = None
        self._client = None
        logger.info("飞书 WebSocket 已停止")

    def _stop_client(self, join_timeout: float) -> None:
        client = self._client
        if client is None:
            return

        for method_name in ("stop", "close"):
            method = getattr(client, method_name, None)
            if callable(method):
                try:
                    method()
                    return
                except Exception as exc:
                    logger.warning("调用飞书 WebSocket client.%s() 失败: %s", method_name, exc)

        disconnect = getattr(client, "_disconnect", None)
        ws_loop = getattr(lark_ws_client, "loop", None)
        if not callable(disconnect) or ws_loop is None or not ws_loop.is_running():
            return

        try:
            future = asyncio.run_coroutine_threadsafe(disconnect(), ws_loop)
            future.result(timeout=max(0.5, join_timeout / 2))
        except Exception as exc:
            logger.warning("关闭飞书 WebSocket 底层连接失败: %s", exc)
        finally:
            try:
                ws_loop.call_soon_threadsafe(ws_loop.stop)
            except RuntimeError as exc:
                logger.warning("停止飞书 WebSocket event loop 失败: %s", exc)

    def _mark_message_processed(self, message_id: str) -> bool:
        now = time.time()
        with self._processed_lock:
            self._prune_processed_messages(now)
            if message_id in self._processed_messages:
                self._processed_messages.move_to_end(message_id)
                return False
            self._processed_messages[message_id] = now
            while len(self._processed_messages) > self._max_processed_messages:
                self._processed_messages.popitem(last=False)
            return True

    def _prune_processed_messages(self, now: float) -> None:
        expired_before = now - self._dedupe_ttl_seconds
        while self._processed_messages:
            _, created_at = next(iter(self._processed_messages.items()))
            if created_at >= expired_before:
                break
            self._processed_messages.popitem(last=False)

    @staticmethod
    def _load_ignored_sender_ids() -> set[str]:
        raw = os.getenv("FEISHU_IGNORE_SENDER_IDS", "")
        return {item.strip() for item in raw.split(",") if item.strip()}


def start_feishu_websocket(
    on_message: Callable[[str, str, str], None],
    app_id: Optional[str] = None,
    app_secret: Optional[str] = None,
    startup_wait_seconds: float = 2.0,
    ignored_sender_ids: Optional[set[str]] = None,
) -> FeishuWebSocket:
    """便捷函数：创建并启动飞书 WebSocket。"""
    ws = FeishuWebSocket(
        app_id=app_id,
        app_secret=app_secret,
        on_message=on_message,
        startup_wait_seconds=startup_wait_seconds,
        ignored_sender_ids=ignored_sender_ids,
    )
    ws.start()
    return ws
