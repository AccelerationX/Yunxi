"""MCP 工具安全治理框架。

借鉴 02_llm_agent_security_sandbox 的四级权限模型与 14_mcp_tool_hub 的风险评估思想，
在 yunxi3.0 内重写，统一所有 MCP 工具的安全策略。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class PermissionLevel(Enum):
    """四级权限模型"""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK = "network"


@dataclass
class SecurityDecision:
    """安全策略判定结果"""
    action: str  # allow / ask / deny
    reason: str
    risk_score: float  # 0.0 - 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "risk_score": self.risk_score,
        }


class SecurityManager:
    """
    MCP 工具的安全策略管理器。

    职责：
    - 维护每个工具的权限级别声明
    - 根据当前运行模式（日常/工厂）动态判定操作是否允许
    - 生成带风险评分和原因的安全决策
    """

    def __init__(self):
        self.tool_permissions: Dict[str, List[PermissionLevel]] = {}
        self.tool_overrides: Dict[str, Dict[str, str]] = {}
        self.global_policy: Dict[str, Dict[PermissionLevel, str]] = {
            "daily_mode": {
                PermissionLevel.READ: "allow",
                PermissionLevel.WRITE: "ask",
                PermissionLevel.EXECUTE: "ask",
                PermissionLevel.NETWORK: "allow",
            },
            "factory_mode": {
                PermissionLevel.READ: "allow",
                PermissionLevel.WRITE: "allow",
                PermissionLevel.EXECUTE: "allow",
                PermissionLevel.NETWORK: "allow",
            },
        }

    def register_tool(
        self,
        tool_name: str,
        permissions: List[PermissionLevel],
    ) -> None:
        """
        注册工具的权限级别声明。

        Args:
            tool_name: 工具名。
            permissions: 该工具涉及的权限级别列表（可多项）。
        """
        self.tool_permissions[tool_name] = permissions

    def register_tool_override(
        self,
        tool_name: str,
        mode: str,
        action: str,
    ) -> None:
        """
        为特定工具在特定模式下注册策略覆盖。

        Args:
            tool_name: 工具名。
            mode: 运行模式（如 daily_mode）。
            action: 覆盖后的动作（allow / ask / deny）。
        """
        if tool_name not in self.tool_overrides:
            self.tool_overrides[tool_name] = {}
        self.tool_overrides[tool_name][mode] = action

    def evaluate(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        context: Optional[Any] = None,
    ) -> SecurityDecision:
        """
        对单个工具调用执行安全策略判定。

        Args:
            tool_name: 被调用工具名。
            arguments: 工具参数（预留用于细粒度参数级风控）。
            context: 运行时上下文，需包含 `mode` 属性（daily_mode / factory_mode）。

        Returns:
            SecurityDecision，包含 action、reason、risk_score。
        """
        perms = self.tool_permissions.get(tool_name, [PermissionLevel.READ])
        mode = getattr(context, "mode", "daily_mode")

        # 检查是否有 tool-level override
        override = self.tool_overrides.get(tool_name, {}).get(mode)
        if override is not None:
            risk_map = {"allow": 0.0, "ask": 0.5, "deny": 1.0}
            risk = risk_map.get(override, 0.5)
            if risk >= 1.0:
                return SecurityDecision(
                    action="deny",
                    reason=f"工具 '{tool_name}' 在当前模式下被显式禁止",
                    risk_score=risk,
                )
            if risk >= 0.5:
                return SecurityDecision(
                    action="ask",
                    reason=f"工具 '{tool_name}' 在当前模式下需要显式确认",
                    risk_score=risk,
                )
            return SecurityDecision(
                action="allow",
                reason="通过显式覆盖策略校验",
                risk_score=0.0,
            )

        policy = self.global_policy.get(mode, self.global_policy["daily_mode"])

        max_risk = 0.0
        blocking_perm: Optional[PermissionLevel] = None

        for perm in perms:
            action = policy.get(perm, "ask")
            risk_map = {"allow": 0.0, "ask": 0.5, "deny": 1.0}
            risk = risk_map.get(action, 0.5)
            if risk > max_risk:
                max_risk = risk
                blocking_perm = perm

        if max_risk >= 1.0:
            return SecurityDecision(
                action="deny",
                reason=(
                    f"工具 '{tool_name}' 需要 {blocking_perm.value if blocking_perm else '未知'} "
                    f"权限，当前 {mode} 策略禁止该操作"
                ),
                risk_score=max_risk,
            )

        if max_risk >= 0.5:
            return SecurityDecision(
                action="ask",
                reason=(
                    f"工具 '{tool_name}' 涉及 {blocking_perm.value if blocking_perm else '未知'} "
                    f"操作，需要用户确认"
                ),
                risk_score=max_risk,
            )

        return SecurityDecision(
            action="allow",
            reason="通过安全策略校验",
            risk_score=0.0,
        )
