"""LLM Provider（最小可用版，支持 OpenAI 兼容格式）。

覆盖 MiniMax、Moonshot(Kimi)、OpenAI 等兼容 /v1/chat/completions 的后端。
基于 httpx 实现，不引入额外的 provider SDK。
"""

from __future__ import annotations

import json as json_module
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx


class MessageRole(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """对话消息（兼容 OpenAI function calling 格式）"""
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"role": self.role.value, "content": self.content}
        if self.name:
            result["name"] = self.name
        if self.tool_call_id is not None:
            result["tool_call_id"] = self.tool_call_id
        if self.tool_calls is not None:
            result["tool_calls"] = self.tool_calls
        return result


@dataclass
class ToolDefinition:
    """工具定义（function calling）"""
    name: str
    description: str
    parameters: Dict[str, Any]


@dataclass
class ToolCall:
    """工具调用结果"""
    id: str
    name: str
    arguments: str


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    model: Optional[str] = None


@dataclass
class LLMConfig:
    """LLM 配置"""
    provider: str = "openai"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    max_tokens: int = 1024
    temperature: float = 0.7
    timeout: float = 30.0
    max_retries: int = 3


class OpenAICompatibleProvider:
    """
    OpenAI 兼容格式 Provider。
    支持 OpenAI、Moonshot、MiniMax 等使用相同消息格式的后端。
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def provider_name(self) -> str:
        return self.config.provider.lower()

    async def initialize(self) -> None:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            headers=headers,
            timeout=self.config.timeout,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDefinition]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        if not self._client:
            await self.initialize()

        if self.provider_name == "ollama":
            return await self._complete_ollama(
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
        }

        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ]

        endpoint = "/chat/completions"
        if self.provider_name == "minimax":
            endpoint = "/chatcompletion_v2"

        response = await self._client.post(endpoint, json=payload)
        response.raise_for_status()
        data = response.json()

        choices = data.get("choices")
        if not choices:
            raise RuntimeError(f"LLM provider returned no choices: {data}")
        choice = choices[0]
        message = choice.get("message", {}) or {}

        content = message.get("content", "") or ""
        if not content and self.provider_name == "minimax":
            content = message.get("reasoning_content", "") or ""

        tool_calls = None
        if "tool_calls" in message:
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"],
                )
                for tc in message["tool_calls"]
            ]

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage"),
            model=data.get("model"),
        )

    async def _complete_ollama(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDefinition]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """调用 Ollama 原生 /api/chat 接口。"""
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {
                    "role": msg.role.value,
                    "content": msg.content,
                }
                for msg in messages
                if msg.role in (MessageRole.SYSTEM, MessageRole.USER, MessageRole.ASSISTANT)
            ],
            "stream": False,
            "options": {
                "temperature": temperature if temperature is not None else self.config.temperature,
                "num_predict": max_tokens if max_tokens is not None else self.config.max_tokens,
            },
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ]

        response = await self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        message = data.get("message", {}) or {}
        tool_calls = None
        if message.get("tool_calls"):
            tool_calls = [
                ToolCall(
                    id=tc.get("id", f"ollama_tool_{idx}"),
                    name=tc.get("function", {}).get("name", ""),
                    arguments=json_module.dumps(
                        tc.get("function", {}).get("arguments", {}),
                        ensure_ascii=False,
                    ),
                )
                for idx, tc in enumerate(message["tool_calls"])
            ]
        return LLMResponse(
            content=message.get("content", "") or "",
            tool_calls=tool_calls,
            finish_reason=data.get("done_reason"),
            model=data.get("model"),
        )

    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDefinition]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        if not self._client:
            await self.initialize()

        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
            "stream": True,
        }

        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ]

        endpoint = "/chat/completions"
        if self.provider_name == "minimax":
            endpoint = "/chatcompletion_v2"

        async with self._client.stream("POST", endpoint, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    chunk = json_module.loads(data)
                    delta = chunk["choices"][0].get("delta", {})
                    text = delta.get("content", "") or ""
                    if not text and self.provider_name == "minimax":
                        text = delta.get("reasoning_content", "") or ""
                    if text:
                        yield text


def create_provider(config: LLMConfig) -> OpenAICompatibleProvider:
    """创建 LLM Provider 的工厂函数。"""
    defaults = {
        "openai": "https://api.openai.com/v1",
        "moonshot": "https://api.moonshot.cn/v1",
        "minimax": "https://api.minimax.chat/v1/text",
        "ollama": "http://localhost:11434",
    }
    if config.provider.lower() in defaults and config.base_url == "https://api.openai.com/v1":
        config.base_url = defaults[config.provider.lower()]
    if config.provider.lower() == "ollama":
        config.base_url = config.base_url.rstrip("/")
        if config.base_url.endswith("/v1"):
            config.base_url = config.base_url[:-3]
    return OpenAICompatibleProvider(config)
