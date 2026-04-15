"""飞书 API 客户端。

提供统一的发送接口，支持 text、image、audio 等消息类型。
从 yunxi-ai/feishu.py 适配而来。
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import requests


logger = logging.getLogger(__name__)

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"


class FeishuClient:
    """飞书 API 客户端。"""

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        receiver_id: Optional[str] = None,
        transport: str = "http",
    ):
        self.app_id = app_id or os.getenv("FEISHU_APP_ID", "")
        self.app_secret = app_secret or os.getenv("FEISHU_APP_SECRET", "")
        self.receiver_id = receiver_id or os.getenv("FEISHU_RECEIVER_ID", "")
        self.transport = transport
        self._token: Optional[str] = None
        self._token_expires_at: float = 0

    @property
    def is_configured(self) -> bool:
        """检查是否已配置。"""
        return bool(self.app_id and self.app_secret and self.receiver_id)

    def _get_token(self) -> Optional[str]:
        """获取 tenant access token，带缓存。"""
        now = time.time()
        if self._token and now < self._token_expires_at - 60:
            return self._token

        url = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"
        try:
            resp = requests.post(
                url,
                json={"app_id": self.app_id, "app_secret": self.app_secret},
                timeout=10,
            )
            payload = resp.json()
            if payload.get("code") == 0:
                self._token = payload.get("tenant_access_token", "")
                expires_in = payload.get("expire", 7200)
                self._token_expires_at = now + expires_in
                return self._token
            else:
                logger.error(f"获取飞书 token 失败: {payload.get('msg')}")
        except Exception as e:
            logger.error(f"获取飞书 token 异常: {e}")
        return None

    def _request(
        self,
        method: str,
        url: str,
        *,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        timeout: int = 10,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """发送 HTTP 请求，带重试。"""
        token = self._get_token()
        if not token:
            return {"code": -1, "msg": "token unavailable"}

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        last_error: Dict[str, Any] = {"code": -1, "msg": "unknown"}
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.request(
                    method,
                    url,
                    headers=headers,
                    json=json_data,
                    params=params,
                    timeout=timeout,
                )
                payload = resp.json()
                if payload.get("code") == 0:
                    return payload
                last_error = {"code": payload.get("code", -1), "msg": payload.get("msg", "")}
                if attempt < max_retries:
                    time.sleep(min(2.0, 0.5 * attempt))
            except Exception as e:
                last_error = {"code": -1, "msg": str(e)}
                if attempt < max_retries:
                    time.sleep(min(2.0, 0.5 * attempt))
        return last_error

    def send_text(
        self,
        content: str,
        receive_id: Optional[str] = None,
        receive_id_type: str = "open_id",
    ) -> Dict[str, Any]:
        """发送文本消息。"""
        rid = receive_id or self.receiver_id
        if not rid:
            return {"code": -1, "msg": "缺少 receiver_id"}

        url = f"{FEISHU_API_BASE}/im/v1/messages"
        params = {"receive_id_type": receive_id_type}
        payload = {
            "receive_id": rid,
            "msg_type": "text",
            "content": json.dumps({"text": content}, ensure_ascii=False),
        }
        return self._request("POST", url, json_data=payload, params=params)

    def send_text_to_user(self, content: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """发送文本消息给默认用户。"""
        return self.send_text(content, receive_id=user_id or self.receiver_id)

    def send_image(self, image_key: str, receive_id: Optional[str] = None) -> Dict[str, Any]:
        """发送图片消息。"""
        rid = receive_id or self.receiver_id
        if not rid:
            return {"code": -1, "msg": "缺少 receiver_id"}

        url = f"{FEISHU_API_BASE}/im/v1/messages"
        params = {"receive_id_type": "open_id"}
        payload = {
            "receive_id": rid,
            "msg_type": "image",
            "content": json.dumps({"image_key": image_key}, ensure_ascii=False),
        }
        return self._request("POST", url, json_data=payload, params=params)

    def send_card(
        self,
        card_content: Dict,
        receive_id: Optional[str] = None,
        receive_id_type: str = "open_id",
    ) -> Dict[str, Any]:
        """发送卡片消息。"""
        rid = receive_id or self.receiver_id
        if not rid:
            return {"code": -1, "msg": "缺少 receiver_id"}

        url = f"{FEISHU_API_BASE}/im/v1/messages"
        params = {"receive_id_type": receive_id_type}
        payload = {
            "receive_id": rid,
            "msg_type": "interactive",
            "content": json.dumps(card_content, ensure_ascii=False),
        }
        return self._request("POST", url, json_data=payload, params=params)


# 全局单例
_feishu_client: Optional[FeishuClient] = None


def get_feishu_client() -> FeishuClient:
    """获取飞书客户端单例。"""
    global _feishu_client
    if _feishu_client is None:
        _feishu_client = FeishuClient()
    return _feishu_client


def send_feishu_message(
    content: str,
    receive_id: Optional[str] = None,
    receive_id_type: str = "open_id",
) -> str:
    """便捷函数：发送飞书消息，返回结果描述。"""
    client = get_feishu_client()
    result = client.send_text(content, receive_id=receive_id, receive_id_type=receive_id_type)
    if result.get("code") == 0:
        return f"消息发送成功 (message_id={result.get('data', {}).get('message_id', '')})"
    return f"发送失败 (code={result.get('code')}, msg={result.get('msg')})"
