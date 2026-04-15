"""LLM Adapter。

将 yunxi3.0 ExecutionEngine 所需的 `complete(system, messages, tools)` 接口
映射到内部 LLM Provider 的协议上。
"""

import json as json_module
from typing import Any, Dict, List, Optional

from core.llm.provider import (
    LLMConfig,
    LLMResponse,
    Message,
    MessageRole,
    OpenAICompatibleProvider,
    ToolCall,
    ToolDefinition,
    create_provider,
)
from core.types.message_types import (
    AssistantMessage,
    TextContentBlock,
    ToolResultContentBlock,
    ToolUseBlockData,
    UserMessage,
)


class _AdapterResponse:
    """Adapter 返回给 Engine 的统一响应对象（duck typing）。"""

    def __init__(self, content: str, tool_calls: Optional[List[Any]] = None):
        self.content = content
        self.tool_calls = tool_calls


class LLMAdapter:
    """ExecutionEngine 可用的 LLM 适配器。"""

    def __init__(self, provider: OpenAICompatibleProvider):
        self.provider = provider

    @classmethod
    def from_env(cls, provider: str = "minimax", model: Optional[str] = None) -> "LLMAdapter":
        """从环境变量创建 Adapter（优先用于测试）。"""
        import os

        provider_name = provider.lower()
        key_map = {
            "openai": "OPENAI_API_KEY",
            "moonshot": "MOONSHOT_API_KEY",
            "minimax": "MINIMAX_API_KEY",
            "ollama": "OLLAMA_API_KEY",
        }
        api_key = os.environ.get(key_map.get(provider_name, ""), "")
        if provider_name != "ollama" and not api_key:
            raise ValueError(f"缺少环境变量 {key_map.get(provider_name)}")

        default_models = {
            "openai": "gpt-4o-mini",
            "moonshot": "moonshot-v1-8k",
            "minimax": "minimax-m2.7",
            "ollama": os.environ.get("OLLAMA_MODEL", "qwen3:4b"),
        }
        default_base_urls = {
            "ollama": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        }
        config = LLMConfig(
            provider=provider,
            api_key=api_key,
            base_url=default_base_urls.get(provider_name, "https://api.openai.com/v1"),
            model=model or default_models.get(provider_name, "unknown"),
        )
        return cls(create_provider(config))

    async def complete(
        self,
        system: str,
        messages: List[Any],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> _AdapterResponse:
        """Engine 调用的统一入口。"""
        provider_messages: List[Message] = []
        if system:
            provider_messages.append(Message(role=MessageRole.SYSTEM, content=system))

        for msg in messages:
            provider_messages.extend(self._convert_message(msg))

        provider_tools = None
        if tools:
            provider_tools = [
                ToolDefinition(
                    name=t["function"]["name"],
                    description=t["function"].get("description", ""),
                    parameters=t["function"].get("parameters", {}),
                )
                for t in tools
                if t.get("type") == "function"
            ]

        resp: LLMResponse = await self.provider.complete(
            messages=provider_messages,
            tools=provider_tools,
        )

        tool_calls = None
        if resp.tool_calls:
            tool_calls = [
                _SimpleToolCall(
                    id=tc.id,
                    name=tc.name,
                    arguments=json_module.loads(tc.arguments)
                    if isinstance(tc.arguments, str)
                    else tc.arguments,
                )
                for tc in resp.tool_calls
            ]

        return _AdapterResponse(content=resp.content or "", tool_calls=tool_calls)

    def _convert_message(self, msg: Any) -> List[Message]:
        """将 Engine 内部消息类型转为 Provider 消息类型。"""
        if isinstance(msg, UserMessage):
            content = msg.content
            # 如果 UserMessage 的内容是 ToolResultContentBlock 列表，
            # 需要拆分为多个 role="tool" 的消息（OpenAI 协议要求）
            if isinstance(content, list) and all(
                isinstance(x, ToolResultContentBlock) for x in content
            ):
                return [
                    Message(
                        role=MessageRole("tool"),
                        content=b.content,
                        tool_call_id=b.tool_use_id,
                    )
                    for b in content
                ]
            text = self._extract_text(content)
            return [Message(role=MessageRole.USER, content=text)]

        if isinstance(msg, AssistantMessage):
            content = msg.content
            if isinstance(content, str):
                return [Message(role=MessageRole.ASSISTANT, content=content)]

            texts: List[str] = []
            tool_calls: List[Dict[str, Any]] = []
            for block in content:
                if isinstance(block, TextContentBlock):
                    texts.append(block.text)
                elif isinstance(block, ToolUseBlockData):
                    # 将 ToolUseBlockData 转换为 OpenAI tool_calls 格式
                    tool_calls.append({
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json_module.dumps(block.input, ensure_ascii=False),
                        },
                    })

            assistant_msg = Message(
                role=MessageRole.ASSISTANT,
                content="".join(texts) if texts else "",
            )
            if tool_calls:
                assistant_msg.tool_calls = tool_calls
            return [assistant_msg]

        # 兜底：假设是原始 dict 或已有 to_dict 方法
        if hasattr(msg, "role") and hasattr(msg, "content"):
            return [Message(role=MessageRole(msg.role), content=str(msg.content))]

        return []

    def _extract_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, TextContentBlock):
                    parts.append(item.text)
                elif isinstance(item, ToolResultContentBlock):
                    parts.append(item.content)
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(parts)
        return str(content)


class _SimpleToolCall:
    """简化的 tool call 对象，供 Engine 使用。"""

    def __init__(self, id: str, name: str, arguments: Dict[str, Any]):
        self.id = id
        self.name = name
        self.arguments = arguments
