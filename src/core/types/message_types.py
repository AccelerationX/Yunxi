"""对话消息类型定义。

为 ExecutionEngine、MCP Hub、LLM 适配层提供统一的消息结构。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class TextContentBlock:
    """文本内容块"""
    text: str


@dataclass
class ToolUseBlockData:
    """LLM 请求调用工具的数据块"""
    id: str
    name: str
    input: Dict[str, Any]


@dataclass
class ToolResultContentBlock:
    """工具执行结果内容块"""
    tool_use_id: str
    content: str
    is_error: bool = False


@dataclass
class UserMessage:
    """用户消息"""
    content: Union[str, List[Any]]


@dataclass
class AssistantMessage:
    """助手消息，可包含文本或 tool_use 请求"""
    content: Union[str, List[Any]]
