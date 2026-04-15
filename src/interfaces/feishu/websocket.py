"""飞书 WebSocket 客户端。

使用 lark-oapi 库建立长连接，接收飞书消息并回调处理。
从 yunxi-ai/feishu_websocket.py 适配而来。
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from typing import Any, Callable, Dict, Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1


logger = logging.getLogger(__name__)


class FeishuWebSocket:
    """飞书 WebSocket 客户端。"""

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        on_message: Optional[Callable[[str, str, str], None]] = None,
        # on_message(user_id, chat_id, content) -> None
    ):
        self.app_id = app_id or os.getenv("FEISHU_APP_ID", "")
        self.app_secret = app_secret or os.getenv("FEISHU_APP_SECRET", "")
        self._on_message = on_message
        self._client: Optional[lark.ws.Client] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._processed_messages: set = set()
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

            # 消息去重
            with self._processed_lock:
                if message_id in self._processed_messages:
                    return
                self._processed_messages.add(message_id)
                if len(self._processed_messages) > 2000:
                    self._processed_messages.clear()

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
                    logger.exception(f"WebSocket 异常: {e}")
                finally:
                    self._running = False

            self._thread = threading.Thread(target=run_ws, daemon=True)
            self._thread.start()

            # 等待连接建立
            time.sleep(2)
            logger.info("飞书 WebSocket 已启动")
            return True

        except Exception as e:
            logger.exception(f"启动飞书 WebSocket 失败: {e}")
            return False

    def stop(self) -> None:
        """停止 WebSocket 连接。"""
        self._running = False
        logger.info("飞书 WebSocket 已停止")


def start_feishu_websocket(
    on_message: Callable[[str, str, str], None],
    app_id: Optional[str] = None,
    app_secret: Optional[str] = None,
) -> FeishuWebSocket:
    """便捷函数：创建并启动飞书 WebSocket。"""
    ws = FeishuWebSocket(
        app_id=app_id,
        app_secret=app_secret,
        on_message=on_message,
    )
    ws.start()
    return ws
