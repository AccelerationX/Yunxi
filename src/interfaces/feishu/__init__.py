"""飞书接口模块。

提供飞书消息的发送和接收能力，作为云汐的日常模式消息通道。
"""

from interfaces.feishu.client import FeishuClient, get_feishu_client
from interfaces.feishu.adapter import FeishuAdapter
from interfaces.feishu.websocket import start_feishu_websocket

__all__ = [
    "FeishuClient",
    "get_feishu_client",
    "FeishuAdapter",
    "start_feishu_websocket",
]
