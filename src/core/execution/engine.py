"""云汐 3.0 统一执行引擎。

职责：维护对话上下文 → 技能快速路径检查 → 调用 LLM →
通过 MCP Hub 处理 tool use → 返回最终结果。
"""

import json
import logging
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from core.mcp.hub import MCPHub
from core.types.message_types import (
    AssistantMessage,
    TextContentBlock,
    ToolResultContentBlock,
    ToolUseBlockData,
    UserMessage,
)


logger = logging.getLogger(__name__)


@dataclass
class EngineConfig:
    """执行引擎配置"""
    max_turns: int = 10
    recent_message_limit: int = 20
    enable_tool_use: bool = True
    enable_skill_fastpath: bool = True


@dataclass
class ExecutionResult:
    """单轮执行结果"""
    content: str
    tool_calls_used: List[str] = field(default_factory=list)
    skill_used: Optional[str] = None
    error: Optional[str] = None


class ConversationContext:
    """简化的对话上下文管理器"""

    def __init__(self, limit: int = 20):
        self.messages: List[Any] = []
        self.limit = limit
        self.turn_count: int = 0

    def add_user_message(self, text: str) -> None:
        """添加用户文本消息。"""
        self.messages.append(UserMessage(content=text))
        self._trim()

    def add_assistant_message(self, text: str) -> None:
        """添加助手文本消息。"""
        self.messages.append(AssistantMessage(content=[TextContentBlock(text=text)]))
        self._trim()
        self.turn_count += 1

    def add_tool_use(self, tool_use_blocks: List[Any]) -> None:
        """添加助手发起的 tool_use 消息。"""
        self.messages.append(AssistantMessage(content=tool_use_blocks))
        self._trim()

    def add_tool_results(self, tool_results: List[Any]) -> None:
        """添加工具执行结果消息（作为 UserMessage 内容）。"""
        blocks = [r for r in tool_results if isinstance(r, ToolResultContentBlock)]
        if blocks:
            self.messages.append(UserMessage(content=blocks))
        self._trim()

    def get_messages(self) -> List[Any]:
        """获取当前维护的消息列表。"""
        return self.messages

    def _trim(self) -> None:
        """按 limit 截断最早的消息。"""
        if len(self.messages) > self.limit:
            self.messages = self.messages[-self.limit :]


class YunxiExecutionEngine:
    """云汐 3.0 统一执行引擎。"""

    def __init__(
        self,
        llm: Any,
        mcp_hub: MCPHub,
        memory_manager: Any,
        config: Optional[EngineConfig] = None,
    ):
        self.llm = llm
        self.mcp_hub = mcp_hub
        self.memory = memory_manager
        self.config = config or EngineConfig()
        self.context = ConversationContext(limit=self.config.recent_message_limit)

    async def respond(
        self,
        user_input: str,
        system_prompt: str,
        runtime_context: Any,
    ) -> ExecutionResult:
        """处理一轮用户输入，返回最终回复。"""
        if user_input:
            self.context.add_user_message(user_input)

        try:
            pending_result = await self._handle_pending_confirmation_message(
                user_input,
                runtime_context,
            )
            if pending_result is not None:
                return pending_result

            # 技能快速路径
            if user_input and self.config.enable_skill_fastpath and self.memory:
                skill_match = await self.memory.try_skill(user_input)
                if skill_match:
                    return await self._execute_skill_path(
                        skill_match, user_input, runtime_context, system_prompt
                    )

            # LLM 通用路径
            for turn in range(self.config.max_turns):
                messages = self.context.get_messages()
                available_tools = (
                    await self.mcp_hub.client.get_tool_descriptions_for_llm()
                    if self.config.enable_tool_use
                    else None
                )

                response = await self.llm.complete(
                    system=system_prompt,
                    messages=messages,
                    tools=available_tools if self.config.enable_tool_use else None,
                )

                assistant_text = response.content or ""
                tool_calls = getattr(response, "tool_calls", None) or []

                if not tool_calls:
                    self.context.add_assistant_message(assistant_text)
                    self._record_chat_experience(
                        user_input, assistant_text, success=True
                    )
                    return ExecutionResult(content=assistant_text)

                # 记录 assistant 的 tool_use 消息
                tool_use_blocks = []
                for tc in tool_calls:
                    tool_use_blocks.append(
                        ToolUseBlockData(
                            id=getattr(tc, "id", ""),
                            name=getattr(tc, "name", ""),
                            input=getattr(tc, "arguments", {}),
                        )
                    )
                self.context.add_tool_use(tool_use_blocks)

                # 通过 MCP Hub 执行工具链
                chain_result = await self.mcp_hub.execute_tool_calls(
                    tool_calls, runtime_context, inferred_intent=user_input
                )
                self._add_chain_results_to_context(chain_result.results)

                pending = self._pending_confirmation_from_results(chain_result.results)
                if pending:
                    response_text = self._pending_confirmation_message(pending)
                    self.context.add_assistant_message(response_text)
                    return ExecutionResult(content=response_text)

                # 如果最后一轮且全部失败，返回错误提示
                if turn == self.config.max_turns - 1:
                    errors = [
                        r.get("error", "")
                        for r in chain_result.results
                        if r.get("is_error")
                    ]
                    if errors:
                        fallback = self._friendly_tool_failure()
                        self.context.add_assistant_message(fallback)
                        return ExecutionResult(
                            content=fallback,
                            error="; ".join(errors),
                        )

            return ExecutionResult(
                content=self._friendly_tool_failure(),
                error="max_turns_exceeded",
            )

        except Exception as exc:
            logger.exception("ExecutionEngine response failed")
            self._record_chat_experience(user_input, "", success=False, error=str(exc))
            return ExecutionResult(
                content=self._friendly_engine_failure(),
                error=str(exc),
            )

    async def _execute_skill_path(
        self,
        skill_match: Dict[str, Any],
        user_input: str,
        runtime_context: Any,
        system_prompt: str,
    ) -> ExecutionResult:
        """执行技能快速路径。"""
        results: List[Dict[str, Any]] = []
        all_success = True
        skill_name = skill_match.get("skill_name", "unknown")

        for action in skill_match.get("actions", []):
            tc = SimpleNamespace(
                id=f"skill_{skill_name}",
                name=action.get("tool", ""),
                arguments=action.get("args", {}),
            )
            chain_result = await self.mcp_hub.execute_tool_calls([tc], runtime_context)
            result = (
                chain_result.results[0]
                if chain_result.results
                else {"error": "无返回", "is_error": True}
            )
            results.append(result)
            if result.get("is_error"):
                all_success = False

        pending = self._pending_confirmation_from_results(results)
        if pending:
            response_text = self._pending_confirmation_message(pending)
            self.context.add_assistant_message(response_text)
            return ExecutionResult(content=response_text, skill_used=skill_name)

        response_text = await self._build_skill_response_via_llm(
            skill_match=skill_match,
            user_input=user_input,
            system_prompt=system_prompt,
            results=results,
            all_success=all_success,
        )

        if self.memory:
            self.memory.record_skill_outcome(skill_name, all_success)
            self.memory.record_experience(
                intent_text=user_input,
                actions=skill_match.get("actions", []),
                outcome="success" if all_success else "failure",
                source="skill_fastpath",
                failure_reason=""
                if all_success
                else results[-1].get("error", ""),
            )

        self.context.add_assistant_message(response_text)
        return ExecutionResult(content=response_text, skill_used=skill_name)

    async def _build_skill_response_via_llm(
        self,
        *,
        skill_match: Dict[str, Any],
        user_input: str,
        system_prompt: str,
        results: List[Dict[str, Any]],
        all_success: bool,
    ) -> str:
        """Let the LLM turn skill execution results into a natural reply."""
        summary = json.dumps(results, ensure_ascii=False)
        guidance = (
            "刚才的快捷能力已经处理完。请用云汐的自然语气回复远，"
            "只说结果和必要的下一步，不要暴露内部字段、系统提示或技术错误。"
            f"\n用户原话：{user_input}\n处理是否成功：{all_success}\n结果摘要：{summary}"
        )
        try:
            response = await self.llm.complete(
                system=system_prompt,
                messages=self.context.get_messages() + [UserMessage(content=guidance)],
                tools=None,
            )
            if response.content:
                return response.content
        except Exception as exc:
            logger.warning("Skill response LLM finalization failed: %s", exc)
        return self._select_skill_response(
            skill_match=skill_match,
            all_success=all_success,
            last_error=results[-1].get("error") if results else None,
        )

    async def _handle_pending_confirmation_message(
        self,
        user_input: str,
        runtime_context: Any,
    ) -> Optional[ExecutionResult]:
        if not user_input or not self.mcp_hub.has_pending_confirmations():
            return None
        if self._is_confirmation_rejection(user_input):
            self.mcp_hub.reject_latest_pending()
            response = "好，那我先不动它。你想继续的时候再跟我说一声就行。"
            self.context.add_assistant_message(response)
            return ExecutionResult(content=response)
        if not self._is_confirmation_acceptance(user_input):
            return None

        chain_result = await self.mcp_hub.approve_latest_pending(runtime_context)
        self._add_chain_results_to_context(chain_result.results)
        if any(result.get("is_error") for result in chain_result.results):
            response = self._friendly_tool_failure()
            error = "; ".join(
                result.get("error", "")
                for result in chain_result.results
                if result.get("is_error")
            )
            self.context.add_assistant_message(response)
            return ExecutionResult(content=response, error=error)
        response = "好，我已经按你点头的那一步处理好了。"
        self.context.add_assistant_message(response)
        return ExecutionResult(
            content=response,
            tool_calls_used=[
                result.get("call_id", "")
                for result in chain_result.results
                if result.get("call_id")
            ],
        )

    def _pending_confirmation_from_results(
        self,
        results: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        for result in results:
            if result.get("pending_confirmation"):
                return result
        return None

    def _pending_confirmation_message(self, pending: Dict[str, Any]) -> str:
        return (
            "这一步会改动你的电脑状态，我想先等你点头。"
            "你回复“确认”我就继续，回复“取消”我就先放下。"
        )

    def _friendly_tool_failure(self) -> str:
        return "远，这一步我刚刚没能稳稳办成。我先停住，不乱动你的电脑；你换个说法或等我再试一次。"

    def _friendly_engine_failure(self) -> str:
        return "远，我这边刚刚卡了一下，但我已经停住了。你再跟我说一遍，我重新陪你处理。"

    def _is_confirmation_acceptance(self, text: str) -> bool:
        normalized = text.strip().lower()
        return normalized in {"确认", "同意", "可以", "继续", "好", "ok", "yes", "y"}

    def _is_confirmation_rejection(self, text: str) -> bool:
        normalized = text.strip().lower()
        return normalized in {"取消", "不要", "先别", "不用", "否", "no", "n"}

    def _select_skill_response(
        self,
        skill_match: Dict[str, Any],
        all_success: bool,
        last_error: Optional[str],
    ) -> str:
        """根据技能类型和执行结果选择情感化的回复变体。"""
        if not all_success:
            return self._friendly_tool_failure()

        skill_name = skill_match.get("skill_name", "")
        actions = skill_match.get("actions", [])
        tool_name = actions[0].get("tool", "") if actions else ""

        # 根据技能/工具类型选择成功回复变体
        if "clipboard" in tool_name or "clipboard" in skill_name:
            return self._pick_variant([
                "好呀，已经复制好了～",
                "搞定，剪贴板这边已经准备好了～",
                "嗯嗯，复制好了，随时可以贴过去哦",
            ], skill_name)
        if "notify" in tool_name or "notification" in skill_name:
            return self._pick_variant([
                "通知已经发出去了～",
                "好啦，通知已经送到了",
                "嗯，已经提醒他了，应该很快能看到",
            ], skill_name)
        if "screenshot" in tool_name or "截图" in skill_name:
            return self._pick_variant([
                "截图好了～你要看看吗？",
                "好呀，已经截下来了",
                "截好了，看看是不是你想要的",
            ], skill_name)
        if "window" in tool_name or "focus" in tool_name or "minimize" in tool_name:
            return self._pick_variant([
                "好啦，窗口已经弄好了～",
                "嗯，搞定了",
                "已经帮你弄好了",
            ], skill_name)
        if "launch" in tool_name or "app" in tool_name:
            return self._pick_variant([
                "应用已经启动啦～",
                "好呀，打开了哦",
                "启动好了，慢慢用～",
            ], skill_name)

        # 默认变体
        return self._pick_variant([
            "好呀，已经帮你弄好了～",
            "嗯嗯，搞定了～",
            "好啦，已经处理好了",
        ], skill_name)

    def _pick_variant(self, variants: List[str], skill_name: str) -> str:
        """从变体列表中基于 skill_name 哈希选择一个（确定性，利于测试）。"""
        seed = sum(ord(c) for c in skill_name) if skill_name else 0
        idx = seed % len(variants)
        return variants[idx]

    def _add_chain_results_to_context(self, results: List[Dict[str, Any]]) -> None:
        """将 MCPHub 返回结果转为 ToolResultContentBlock 并加入上下文。"""
        result_blocks: List[ToolResultContentBlock] = []
        for result in results:
            result_blocks.append(
                ToolResultContentBlock(
                    tool_use_id=result.get("call_id", ""),
                    content=result.get("content") or result.get("error", ""),
                    is_error=result.get("is_error", False),
                )
            )
        self.context.add_tool_results(result_blocks)

    def _record_chat_experience(
        self, user_input: str, response_text: str, success: bool, error: str = ""
    ) -> None:
        """记录聊天经验。"""
        if self.memory:
            self.memory.record_experience(
                intent_text=user_input,
                actions=[{"type": "chat_response", "content": response_text}],
                outcome="success" if success else "failure",
                source="chat",
                failure_reason=error,
            )

    def reset_context(self) -> None:
        """重置对话上下文。"""
        self.context = ConversationContext(limit=self.config.recent_message_limit)
