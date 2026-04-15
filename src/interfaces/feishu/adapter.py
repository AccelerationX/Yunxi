"""飞书适配器。

桥接飞书消息与 YunxiRuntime：
- 接收飞书消息 → 调用 runtime.chat() → 发送飞书回复
- 主动消息 → 直接发送飞书消息
"""

from __future__ import annotations

import asyncio
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
    ):
        self.runtime = runtime
        self.feishu_client = feishu_client or get_feishu_client()
        self.proactive_callback = proactive_callback
        self._proactive_lock = asyncio.Lock()

    async def handle_message(self, user_id: str, chat_id: str, content: str) -> None:
        """处理收到的飞书消息。"""
        logger.info(f"FeishuAdapter 处理消息: {content[:50]}...")

        try:
            # 调用 runtime.chat() 获取回复
            response = await self.runtime.chat(content)

            if response:
                # 发送回复到飞书
                self.feishu_client.send_text(
                    content=response,
                    receive_id=chat_id,
                    receive_id_type="chat_id",
                )
                logger.info(f"已发送回复: {response[:50]}...")
            else:
                logger.warning("runtime.chat() 返回空内容")

        except Exception as e:
            logger.exception(f"处理飞书消息异常: {e}")
            # 发送错误回复
            self.feishu_client.send_text(
                content=f"抱歉，处理出错了：{str(e)[:100]}",
                receive_id=chat_id,
                receive_id_type="chat_id",
            )

    def on_feishu_message(self, user_id: str, chat_id: str, content: str) -> None:
        """同步入口，供 WebSocket 回调使用。"""
        # 在新线程中运行异步处理
        asyncio.create_task(self.handle_message(user_id, chat_id, content))

    async def send_proactive_message(self, message: str) -> None:
        """发送主动消息到飞书。"""
        if not message:
            return

        async with self._proactive_lock:
            try:
                result = self.feishu_client.send_text_to_user(message)
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
