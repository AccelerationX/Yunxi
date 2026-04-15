"""MCP 工具调用审计日志。

记录每一次 MCP 工具链的执行过程、结果与安全决策，支持后续查询与终身学习数据导入。
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


class AuditLogger:
    """
    MCP 审计日志管理器。

    职责：
    - 将每次工具链执行记录持久化为 JSONL 格式
    - 支持按日期分文件存储
    - （可选）与 MemoryManager 联动，同步写入 ExperienceBuffer
    """

    def __init__(
        self,
        log_dir: str = "logs/mcp_audit",
        memory_manager: Optional[Any] = None,
    ):
        self.log_dir = log_dir
        self.memory_manager = memory_manager
        os.makedirs(log_dir, exist_ok=True)
        self.log_path = os.path.join(
            log_dir,
            f"audit_{datetime.now().strftime('%Y%m%d')}.jsonl",
        )

    async def record(
        self,
        plan: List[Any],
        results: List[Dict[str, Any]],
        security_decisions: List[Dict[str, Any]],
        inferred_intent: Optional[str] = None,
    ) -> str:
        """
        记录一次工具链执行到审计日志。

        Args:
            plan: 执行计划列表（元素需有 tool_name / arguments / call_id 属性）。
            results: 执行结果列表。
            security_decisions: 安全决策列表。
            inferred_intent: 推断出的用户意图文本（用于终身学习）。

        Returns:
            本次记录的唯一 log_id。
        """
        log_id = f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        entry = {
            "log_id": log_id,
            "timestamp": datetime.now().isoformat(),
            "plan": [
                {
                    "tool": getattr(p, "tool_name", "unknown"),
                    "args": getattr(p, "arguments", {}),
                    "id": getattr(p, "call_id", ""),
                }
                for p in plan
            ],
            "results": results,
            "security": security_decisions,
        }

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # 同步写入 ExperienceBuffer（如果已绑定 MemoryManager）
        if self.memory_manager is not None and inferred_intent is not None:
            actions = [
                {"tool": p.tool_name, "args": p.arguments}
                for p in plan
                if hasattr(p, "tool_name")
            ]
            all_success = all(not r.get("is_error", False) for r in results)
            failure_reason = ""
            if not all_success:
                failure_reason = "; ".join(
                    r.get("error", "") for r in results if r.get("is_error")
                )

            self.memory_manager.record_experience(
                intent_text=inferred_intent,
                actions=actions,
                outcome="success" if all_success else "failure",
                source="mcp_audit",
                failure_reason=failure_reason,
            )

        return log_id

    def get_today_entries(self) -> List[Dict[str, Any]]:
        """读取当天的所有审计记录。"""
        entries: List[Dict[str, Any]] = []
        if not os.path.exists(self.log_path):
            return entries

        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries
