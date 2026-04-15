"""MCP stdio Client 封装。

基于官方 mcp 库封装，支持多 Server 连接、统一工具发现与调用。
所有 Server 生命周期由本类统一管理。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool


@dataclass
class ServerConnection:
    """单个 MCP Server 的连接上下文"""
    stdio_cm: Any
    session_cm: Any
    session: ClientSession
    tools: List[Tool] = field(default_factory=list)


class MCPClient:
    """
    云汐 3.0 的 MCP 统一客户端。

    职责：
    - 启动并维护一个或多个 MCP Server 的 stdio 连接
    - 聚合所有 Server 的工具列表
    - 按工具名路由到对应的 Server 执行调用
    """

    def __init__(self):
        self._connections: Dict[str, ServerConnection] = {}
        self._tool_to_server: Dict[str, str] = {}

    async def connect_server(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        连接一个 MCP Server。

        Args:
            name: Server 的本地标识名，用于后续管理。
            command: 启动 Server 的可执行文件路径。
            args: 启动参数列表。
            env: 额外环境变量。

        Raises:
            ConnectionError: Server 启动失败或初始化超时。
        """
        params = StdioServerParameters(
            command=command,
            args=args or [],
            env=env,
        )

        stdio_cm = stdio_client(params)
        read, write = await stdio_cm.__aenter__()

        session_cm = ClientSession(read, write)
        session = await session_cm.__aenter__()
        await session.initialize()

        tools_result = await session.list_tools()
        tools = tools_result.tools

        self._connections[name] = ServerConnection(
            stdio_cm=stdio_cm,
            session_cm=session_cm,
            session=session,
            tools=tools,
        )

        for tool in tools:
            self._tool_to_server[tool.name] = name

    async def disconnect_server(self, name: str) -> None:
        """断开指定 Server 的连接。"""
        conn = self._connections.pop(name, None)
        if conn is None:
            return

        for tool in conn.tools:
            if self._tool_to_server.get(tool.name) == name:
                self._tool_to_server.pop(tool.name, None)

        try:
            await conn.session_cm.__aexit__(None, None, None)
        except RuntimeError:
            # 在跨任务清理时（如 pytest fixture teardown）可能触发 anyio CancelScope 任务检查
            pass
        try:
            await conn.stdio_cm.__aexit__(None, None, None)
        except RuntimeError:
            pass

    async def disconnect_all(self) -> None:
        """断开所有 Server 的连接。"""
        for name in list(self._connections.keys()):
            await self.disconnect_server(name)

    async def list_tools(self) -> List[Tool]:
        """返回所有已连接 Server 提供的工具的聚合列表。"""
        all_tools: List[Tool] = []
        for conn in self._connections.values():
            all_tools.extend(conn.tools)
        return all_tools

    def list_tool_names(self) -> List[str]:
        """返回所有已注册工具名。"""
        return list(self._tool_to_server.keys())

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        调用指定工具。

        Args:
            tool_name: 工具名。
            arguments: 工具参数字典。

        Returns:
            mcp.types.CallToolResult 原始结果对象。

        Raises:
            ValueError: 工具名未在已连接的 Server 中注册。
            RuntimeError: 调用过程中连接断开或 Server 异常退出。
        """
        server_name = self._tool_to_server.get(tool_name)
        if server_name is None:
            raise ValueError(f"未知工具: {tool_name}")

        conn = self._connections[server_name]
        result = await conn.session.call_tool(tool_name, arguments=arguments)
        return result

    def has_tool(self, tool_name: str) -> bool:
        """检查指定工具是否已在已连接的 Server 中注册。"""
        return tool_name in self._tool_to_server

    async def get_tool_descriptions_for_llm(self) -> List[Dict[str, Any]]:
        """
        将 MCP 工具描述转换为 LLM function calling 所需的 schema 格式。

        Returns:
            符合 OpenAI function schema 的字典列表。
        """
        tools = await self.list_tools()
        descriptions: List[Dict[str, Any]] = []
        for tool in tools:
            descriptions.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema,
                },
            })
        return descriptions
