# 云汐 3.0 执行层简化设计文档（MCP 适配版）

> **定位**：统一、简化的执行引擎，负责对话流转、MCP 工具链调用、异常处理。  
> **核心原则**：删除过度工程化，保留核心能力；所有工具调用统一通过 MCP Hub 进行，让每一行代码的行为都可预测。

---

## 一、设计目标

1. **单一后端**：彻底删除 V1/V2 双轨制，只保留一个 `YunxiExecutionEngine`。
2. **MCP 统一入口**：不直接调用任何工具，所有 tool use 请求必须经过 `MCPHub` 的编排、安全校验和审计。
3. **可预测的错误处理**：只有两种异常处理策略——重试一次、失败报错。删除未实际触发的复杂恢复分支。
4. **上下文管理直白化**：直接用 `List[Message]` 维护最近 N 轮对话，不再使用不可变 State Machine。
5. **技能快速路径**：执行前优先检查 `SkillLibrary`，高匹配度时直接执行技能动作序列，绕过 LLM 通用推理。

---

## 二、从 yunxi2.0 继承与修改

### 2.1 继承内容

- `core/types/message_types.py` 中的消息类型定义：`UserMessage`, `AssistantMessage`, `ToolUseBlock`, `ToolResultContentBlock` 等。这些类型定义清晰，可直接复用。
- `core/execution/query_loop.py` 中的核心 LLM 调用 + Tool Use 循环思路：这个模式本身是正确的，但实现过于复杂。

### 2.2 需要修改的内容

#### 问题 1：V1/V2 双轨制 + 工具直接调用
- 2.0 的执行引擎直接持有工具字典并调用 `tool.execute()`，与具体工具实现强耦合。
- 3.0 改为通过 `MCPHub` 统一调用，引擎只与 `MCPHub` 的协议接口交互。

#### 问题 2：`QueryLoop` 分支爆炸
- `query_loop.py` 嵌套了 8+ 个分支，且 `MaxOutputTokensError` / `PromptTooLongError` 恢复逻辑是死代码。

#### 问题 3：`LLMProviderAdapter` 伪流式
- `stream_completion` 内部调用阻塞式 `provider.complete()`，然后一次性 yield 完整结果。

### 2.3 3.0 的修正策略

| 2.0 组件 | 3.0 处理 |
|---------|---------|
| `query_engine.py` (V1) | **彻底删除** |
| `context_manager.py` (V1) | **彻底删除** |
| `query_loop_executor.py` | **彻底删除**，功能合并到新的 `YunxiExecutionEngine` |
| `state_machine.py` | 大幅简化，只保留必要的状态描述 |
| `llm_adapter.py` | 保留但修改：如果 provider 不支持真流式，则明确标记为 `complete()` 模式 |
| `tool_executor.py` | 被 `MCPHub` 替代，不再作为引擎的直接依赖 |

---

## 三、接口设计

### 3.1 统一的执行引擎

```python
# core/execution/engine.py
from typing import List, Optional, AsyncGenerator, Any
from dataclasses import dataclass, field

@dataclass
class EngineConfig:
    max_turns: int = 10               # 单轮对话中最多 tool-use 轮数
    recent_message_limit: int = 20    # 保留的最近对话轮数
    enable_tool_use: bool = True
    enable_skill_fastpath: bool = True  # 是否启用技能快速路径

@dataclass
class ExecutionResult:
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
    
    def add_user_message(self, text: str):
        from core.types.message_types import UserMessage
        self.messages.append(UserMessage(content=text))
        self._trim()
    
    def add_assistant_message(self, text: str):
        from core.types.message_types import AssistantMessage, TextContentBlock
        self.messages.append(AssistantMessage(content=[TextContentBlock(text=text)]))
        self._trim()
        self.turn_count += 1
    
    def add_tool_use(self, tool_use_blocks: List[Any]):
        from core.types.message_types import AssistantMessage
        self.messages.append(AssistantMessage(content=tool_use_blocks))
        self._trim()
    
    def add_tool_results(self, tool_results: List[Any]):
        from core.types.message_types import ToolResultContentBlock, UserMessage
        blocks = [r for r in tool_results if isinstance(r, ToolResultContentBlock)]
        if blocks:
            self.messages.append(UserMessage(content=blocks))
        self._trim()
    
    def get_messages(self) -> List[Any]:
        return self.messages
    
    def _trim(self):
        if len(self.messages) > self.limit:
            self.messages = self.messages[-self.limit:]

class YunxiExecutionEngine:
    """
    云汐 3.0 统一执行引擎。
    职责：维护对话上下文 → 技能快速路径检查 → 调用 LLM → 通过 MCP Hub 处理 tool use → 返回最终结果。
    """
    def __init__(
        self,
        llm,
        mcp_hub,                       # MCPHub 实例
        memory_manager,                # 用于 try_skill 和记录经验
        config: Optional[EngineConfig] = None
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
        """
        处理一轮用户输入，返回最终回复。
        """
        self.context.add_user_message(user_input)
        
        try:
            # ========== 技能快速路径 ==========
            if self.config.enable_skill_fastpath and self.memory:
                skill_match = self.memory.try_skill(user_input)
                if skill_match:
                    return await self._execute_skill_path(skill_match, user_input, runtime_context)
            
            # ========== LLM 通用路径 ==========
            for turn in range(self.config.max_turns):
                messages = self.context.get_messages()
                
                # 获取可用工具描述（用于 LLM 的 function calling）
                available_tools = await self.mcp_hub.client.get_tool_descriptions_for_llm()
                
                response = await self.llm.complete(
                    system=system_prompt,
                    messages=messages,
                    tools=available_tools if self.config.enable_tool_use else None
                )
                
                assistant_text = response.content or ""
                tool_calls = getattr(response, 'tool_calls', None) or []
                
                if not tool_calls:
                    self.context.add_assistant_message(assistant_text)
                    self._record_chat_experience(user_input, assistant_text, success=True)
                    return ExecutionResult(content=assistant_text)
                
                # 记录 assistant 的 tool_use 消息
                from core.types.message_types import AssistantMessage, ToolUseBlockData
                tool_use_blocks = []
                for tc in tool_calls:
                    tool_use_blocks.append(ToolUseBlockData(
                        id=tc.id,
                        name=tc.name,
                        input=tc.arguments
                    ))
                self.context.add_tool_use(tool_use_blocks)
                
                # 通过 MCP Hub 执行工具链
                chain_result = await self.mcp_hub.execute_tool_calls(tool_calls, runtime_context)
                
                # 将 tool results 转为 ToolResultContentBlock 并加入上下文
                self._add_chain_results_to_context(chain_result.results)
                
                # 如果工具链全部失败且是最后一轮，返回错误提示
                if turn == self.config.max_turns - 1:
                    errors = [r.get("error", "") for r in chain_result.results if r.get("is_error")]
                    if errors:
                        self.context.add_assistant_message("[工具执行遇到问题，请换个方式说吧]")
                        return ExecutionResult(
                            content="[工具执行遇到问题，请换个方式说吧]",
                            error="; ".join(errors)
                        )
            
            return ExecutionResult(
                content="[尝试使用工具多次仍未完成]",
                error="max_turns_exceeded"
            )
            
        except Exception as e:
            self._record_chat_experience(user_input, "", success=False, error=str(e))
            return ExecutionResult(
                content=f"[云汐这里出了点小问题：{e}]",
                error=str(e)
            )
    
    async def _execute_skill_path(self, skill_match: Dict[str, Any], user_input: str, runtime_context: Any) -> ExecutionResult:
        """执行技能快速路径"""
        results = []
        all_success = True
        
        for action in skill_match["actions"]:
            # 构造单个 tool call
            tc = SimpleNamespace(
                id=f"skill_{skill_match['skill_name']}",
                name=action["tool"],
                arguments=action["args"],
            )
            chain_result = await self.mcp_hub.execute_tool_calls([tc], runtime_context)
            result = chain_result.results[0] if chain_result.results else {"error": "无返回", "is_error": True}
            results.append(result)
            if result.get("is_error"):
                all_success = False
        
        # 记录技能结果
        self.memory.record_skill_outcome(skill_match["skill_name"], all_success)
        self.memory.record_experience(
            intent_text=user_input,
            actions=skill_match["actions"],
            outcome="success" if all_success else "failure",
            source="skill_fastpath",
            failure_reason="" if all_success else results[-1].get("error", ""),
        )
        
        # 构建自然语言回复（可后续优化为基于技能类型的模板回复）
        if all_success:
            response_text = f"好呀，已经帮你弄好了～"
        else:
            response_text = f"哎呀，这个操作好像没成功，{results[-1].get('error', '不知道哪里出了问题')}"
        
        self.context.add_assistant_message(response_text)
        return ExecutionResult(
            content=response_text,
            skill_used=skill_match["skill_name"]
        )
    
    def _add_chain_results_to_context(self, results: List[Dict[str, Any]]):
        from core.types.message_types import ToolResultContentBlock
        result_blocks = []
        for r in results:
            result_blocks.append(ToolResultContentBlock(
                tool_use_id=r["call_id"],
                content=r.get("content") or r.get("error", ""),
                is_error=r.get("is_error", False)
            ))
        self.context.add_tool_results(result_blocks)
    
    def _record_chat_experience(self, user_input: str, response_text: str, success: bool, error: str = ""):
        if self.memory:
            self.memory.record_experience(
                intent_text=user_input,
                actions=[{"type": "chat_response", "content": response_text}],
                outcome="success" if success else "failure",
                source="chat",
                failure_reason=error,
            )
    
    def reset_context(self):
        self.context = ConversationContext(limit=self.config.recent_message_limit)
```

---

## 四、与 MCP Hub 的交互协议

### 4.1 `MCPHub` 需要暴露给 Engine 的接口

```python
class MCPHub:
    # ... 其他方法 ...
    
    async def execute_tool_calls(self, tool_calls: List[Any], context: Any) -> ToolChainResult:
        """执行 LLM 输出的 tool_calls 列表"""
        ...
    
    async def execute_single(self, tool_name: str, arguments: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """执行单个工具调用（用于技能快速路径）"""
        tc = SimpleNamespace(id=f"single_{tool_name}", name=tool_name, arguments=arguments)
        chain_result = await self.execute_tool_calls([tc], context)
        return chain_result.results[0] if chain_result.results else {"error": "无返回", "is_error": True}
```

### 4.2 LLM 的 tool description 获取

```python
# core/mcp/client.py（需暴露给 LLM 的方法）
class MCPClient:
    async def get_tool_descriptions_for_llm(self) -> List[Dict[str, Any]]:
        """
        将 MCP Server 提供的工具描述转换为 LLM 可用的 function schema。
        """
        tools = await self.list_tools()
        descriptions = []
        for t in tools:
            descriptions.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.inputSchema,
                }
            })
        return descriptions
```

---

## 五、实施步骤

### Step 1：新建 `core/execution/engine.py`
- 实现 `ConversationContext` 和 `YunxiExecutionEngine`。
- 重点实现 `_execute_skill_path()` 和 `respond()` 中的 MCP 调用逻辑。

### Step 2：删除 V1 兼容层
- 删除 `core/execution/query_engine.py`。
- 删除 `core/execution/context_manager.py`。
- 删除 `core/execution/query_loop_executor.py`。
- 保留 `core/execution/query_loop.py` 作为参考，新 engine 稳定后最终删除。

### Step 3：修改 `daemon/main.py`
- 初始化 `MCPHub` 和 `MemoryManager`（含 SkillLibrary）。
- 将 `YunxiExecutionEngine` 的初始化改为传入 `llm`、`mcp_hub`、`memory_manager`。

### Step 4：流式调用适配
- 修改 `core/execution/llm_adapter.py`：
  - 如果 provider 支持真流式，使用真流式；否则明确走 `complete()` 模式。
- `YunxiExecutionEngine.respond()` 第一阶段先返回完整字符串，后续可扩展为 `AsyncGenerator`。

---

## 六、验收标准

1. `YunxiExecutionEngine.respond(user_input, system_prompt, runtime_context)` 能成功返回字符串，且对话上下文能维持连贯性。
2. 当 LLM 返回 tool calls 时，引擎通过 `MCPHub.execute_tool_calls()` 正确执行，并将结果再次传给 LLM。
3. 当 `SkillLibrary` 中存在高匹配度技能时，引擎走 `_execute_skill_path()`，直接执行 MCP 工具链，不经过 LLM 通用推理。
4. 当工具链执行抛出异常时，不会导致整个对话崩溃，而是把错误信息作为 tool result 返回给 LLM 或用户。
5. 连续 10 轮对话不丢失上下文，第 11 轮时最早的用户消息被截断（`limit=20`）。
6. 通过 `ConversationTester` 进行 5 轮带 MCP 工具调用的对话测试，全部通过。

---

*文档创建时间：2026-04-14*  
*最后更新时间：2026-04-14*  
*版本：v2.0*
