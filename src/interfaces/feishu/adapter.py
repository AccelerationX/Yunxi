"""飞书适配器。

桥接飞书消息与 YunxiRuntime：
- 接收飞书消息 → 调用 runtime.chat() → 发送飞书回复
- 主动消息 → 直接发送飞书消息
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

from interfaces.feishu.client import FeishuClient, get_feishu_client


if TYPE_CHECKING:
    from core.runtime import YunxiRuntime


logger = logging.getLogger(__name__)

# 主动消息回调类型
ProactiveCallback = Callable[[str], Awaitable[None] | None]


class FeishuAdapter:
    """飞书消息适配器。"""

    def __init__(
        self,
        runtime: "YunxiRuntime",
        feishu_client: Optional[FeishuClient] = None,
        proactive_callback: Optional[ProactiveCallback] = None,
        event_loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self.runtime = runtime
        self.feishu_client = feishu_client or get_feishu_client()
        self.proactive_callback = proactive_callback
        self._event_loop = event_loop or self._get_running_loop_or_none()
        self._proactive_lock = asyncio.Lock()

    async def handle_message(self, user_id: str, chat_id: str, content: str) -> None:
        """处理收到的飞书消息。"""
        logger.info(f"FeishuAdapter 处理消息: {content[:50]}...")

        try:
            # 调用 runtime.chat() 获取回复
            response = await self.runtime.chat(content)

            if response:
                # 发送回复到飞书
                result = await asyncio.to_thread(
                    self.feishu_client.send_text,
                    content=response,
                    receive_id=chat_id,
                    receive_id_type="chat_id",
                )
                if result.get("code") == 0:
                    logger.info(f"已发送回复: {response[:50]}...")
                else:
                    logger.warning("飞书回复发送失败: %s", result.get("msg"))
            else:
                logger.warning("runtime.chat() 返回空内容")

        except Exception as e:
            logger.exception(f"处理飞书消息异常: {e}")
            # 发送错误回复
            try:
                await asyncio.to_thread(
                    self.feishu_client.send_text,
                    content="远，我这边刚刚卡了一下，但我已经停住了。你再跟我说一遍，我重新陪你处理。",
                    receive_id=chat_id,
                    receive_id_type="chat_id",
                )
            except Exception as send_error:
                logger.exception(f"发送飞书错误回复异常: {send_error}")

    def on_feishu_message(
        self,
        user_id: str,
        chat_id: str,
        content: str,
    ) -> asyncio.Task[Any] | concurrent.futures.Future[Any]:
        """同步入口，供 WebSocket 线程回调使用。"""
        loop = self._resolve_event_loop()
        coroutine = self.handle_message(user_id, chat_id, content)
        running_loop = self._get_running_loop_or_none()
        if loop is running_loop:
            task = loop.create_task(coroutine)
            task.add_done_callback(self._log_task_exception)
            return task

        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        future.add_done_callback(self._log_future_exception)
        return future

    def bind_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind the adapter to the daemon's main event loop."""
        self._event_loop = loop

    def _resolve_event_loop(self) -> asyncio.AbstractEventLoop:
        loop = self._event_loop
        if loop is not None and not loop.is_closed() and loop.is_running():
            return loop
        running_loop = self._get_running_loop_or_none()
        if running_loop is None:
            raise RuntimeError(
                "FeishuAdapter.on_feishu_message() requires a running event loop; "
                "construct the adapter inside the daemon loop or pass event_loop explicitly."
            )
        self._event_loop = running_loop
        return running_loop

    @staticmethod
    def _get_running_loop_or_none() -> Optional[asyncio.AbstractEventLoop]:
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    @staticmethod
    def _log_task_exception(task: asyncio.Task[Any]) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            logger.warning("飞书消息处理任务已取消")
        except Exception as exc:
            logger.exception("飞书消息处理任务异常: %s", exc)

    @staticmethod
    def _log_future_exception(future: concurrent.futures.Future[Any]) -> None:
        try:
            future.result()
        except concurrent.futures.CancelledError:
            logger.warning("飞书消息处理 future 已取消")
        except Exception as exc:
            logger.exception("飞书消息处理 future 异常: %s", exc)

    async def send_proactive_message(self, message: str) -> None:
        """发送主动消息到飞书。"""
        if not message:
            return

        async with self._proactive_lock:
            try:
                result = await asyncio.to_thread(
                    self.feishu_client.send_text_to_user,
                    message,
                )
                if result.get("code") == 0:
                    logger.info(f"主动消息发送成功: {message[:50]}...")
                else:
                    logger.warning(f"主动消息发送失败: {result.get('msg')}")
            except Exception as e:
                logger.exception(f"发送主动消息异常: {e}")

    def create_proactive_callback(self) -> ProactiveCallback:
        """创建主动消息回调函数。"""
        async def callback(message: str) -> None:
            await self.send_proactive_message(message)

        return callback
