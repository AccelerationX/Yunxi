"""MCP 工具中枢。

整合工具发现、DAG 规划、安全校验、执行与审计，作为云汐 3.0 日常模式的统一工具调用入口。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.mcp.client import MCPClient
from core.mcp.planner import DAGPlanner
from core.mcp.security import SecurityManager
from core.mcp.audit_logger import AuditLogger


@dataclass
class ToolCallPlan:
    """单个工具调用计划"""
    tool_name: str
    arguments: Dict[str, Any]
    call_id: str
    depends_on: List[str] = field(default_factory=list)


@dataclass
class ToolChainResult:
    """工具链执行结果"""
    results: List[Dict[str, Any]]
    audit_log_id: str
    security_decisions: List[Dict[str, Any]]


class MCPHub:
    """
    云汐 3.0 的 MCP 工具中枢。

    职责：
    - 管理 MCP Server 生命周期
    - 对 LLM 输出的 tool_calls 进行安全校验、DAG 排序、执行与审计
    - 提供单个工具快速调用入口
    """

    def __init__(
        self,
        client: MCPClient,
        planner: DAGPlanner,
        security: SecurityManager,
        audit: AuditLogger,
    ):
        self.client = client
        self.planner = planner
        self.security = security
        self.audit = audit
        self._initialized = False

    async def initialize(self, server_configs: List[Dict[str, Any]]) -> None:
        """
        启动所有配置的 MCP Server 并完成工具发现。

        Args:
            server_configs: 每个元素包含 name, command, args, env 字典。
        """
        for cfg in server_configs:
            await self.client.connect_server(
                name=cfg["name"],
                command=cfg["command"],
                args=cfg.get("args", []),
                env=cfg.get("env"),
            )
            # 自动注册安全权限（如配置中声明了 permissions）
            perms = cfg.get("permissions", [])
            if perms:
                from core.mcp.security import PermissionLevel
                for tool_name, perm_strs in perms.items():
                    perm_levels = [PermissionLevel(p) for p in perm_strs]
                    self.security.register_tool(tool_name, perm_levels)

        self._initialized = True

    async def execute_tool_calls(
        self,
        tool_calls: List[Any],
        context: Any,
        inferred_intent: Optional[str] = None,
    ) -> ToolChainResult:
        """
        执行 LLM 输出的一组 tool_calls。

        Args:
            tool_calls: LLM 返回的 tool call 对象列表（需有 name / arguments / id 属性）。
            context: 运行时上下文，用于安全策略判定。
            inferred_intent: 推断出的用户意图，用于审计和终身学习。

        Returns:
            ToolChainResult，包含结果列表、审计日志 ID 和安全决策记录。
        """
        if not self._initialized:
            raise RuntimeError("MCPHub 尚未初始化，请先调用 initialize()")

        plans = [
            ToolCallPlan(
                tool_name=getattr(tc, "name", ""),
                arguments=getattr(tc, "arguments", {}),
                call_id=getattr(tc, "id", ""),
            )
            for tc in tool_calls
        ]

        return await self._execute_plans(plans, context, inferred_intent)

    async def execute_single(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Any,
        inferred_intent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        执行单个工具调用（用于技能快速路径等场景）。

        Returns:
            单个工具的执行结果字典。
        """
        plan = ToolCallPlan(
            tool_name=tool_name,
            arguments=arguments,
            call_id=f"single_{tool_name}",
        )
        chain_result = await self._execute_plans([plan], context, inferred_intent)
        if chain_result.results:
            return chain_result.results[0]
        return {"error": "无返回结果", "is_error": True}

    def list_available_tool_names(self) -> List[str]:
        """返回当前已发现并可路由的 MCP 工具名。"""
        return self.client.list_tool_names()

    async def _execute_plans(
        self,
        plans: List[ToolCallPlan],
        context: Any,
        inferred_intent: Optional[str] = None,
    ) -> ToolChainResult:
        """内部执行逻辑：拓扑排序 → 安全校验 → 执行 → 审计。"""
        ordered_plans = self.planner.topological_sort(plans)

        results: List[Dict[str, Any]] = []
        security_decisions: List[Dict[str, Any]] = []

        for step in ordered_plans:
            decision = self.security.evaluate(
                tool_name=step.tool_name,
                arguments=step.arguments,
                context=context,
            )
            security_decisions.append(decision.to_dict())

            if decision.action == "deny":
                results.append({
                    "call_id": step.call_id,
                    "error": f"安全策略拒绝：{decision.reason}",
                    "is_error": True,
                })
                continue

            if decision.action == "ask":
                results.append({
                    "call_id": step.call_id,
                    "error": f"需要用户确认：{decision.reason}",
                    "is_error": True,
                })
                continue

            if not self.client.has_tool(step.tool_name):
                raise ValueError(f"未知工具: {step.tool_name}")

            try:
                raw_result = await self.client.call_tool(
                    step.tool_name,
                    step.arguments,
                )
                content = self._normalize_result(raw_result)
                results.append({
                    "call_id": step.call_id,
                    "content": content,
                    "is_error": False,
                })
            except Exception as exc:
                results.append({
                    "call_id": step.call_id,
                    "error": f"工具执行异常：{exc}",
                    "is_error": True,
                })

        audit_log_id = await self.audit.record(
            plan=plans,
            results=results,
            security_decisions=security_decisions,
            inferred_intent=inferred_intent,
        )

        return ToolChainResult(
            results=results,
            audit_log_id=audit_log_id,
            security_decisions=security_decisions,
        )

    def _normalize_result(self, raw: Any) -> str:
        """将 MCP 返回结果统一归一化为字符串。"""
        if raw is None:
            return ""

        # MCP 的 CallToolResult 通常有 content 属性（列表）
        if hasattr(raw, "content") and raw.content is not None:
            texts = []
            for item in raw.content:
                if hasattr(item, "text") and item.text is not None:
                    texts.append(item.text)
                else:
                    texts.append(str(item))
            return "\n".join(texts)

        if isinstance(raw, str):
            return raw

        import json
        try:
            return json.dumps(raw, ensure_ascii=False, indent=2)
        except Exception:
            return str(raw)
