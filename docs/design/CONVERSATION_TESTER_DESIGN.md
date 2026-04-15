# 云汐 3.0 对话验证框架设计文档

> **定位**：测试基础设施，以"直接传入指令、观察真实回复"的方式验证云汐的整体行为。  
> **核心原则**：不看函数覆盖率，只看"云汐作为一个整体是否表现正确"。

---

## 一、设计目标

1. **端到端验证**：绕过飞书、Tray 等外部渠道，直接调用运行时核心，获取云汐的真实回复。
2. **状态注入**：测试前可以向记忆、情感、感知等子系统注入预设数据，测试后观察回复是否符合预期。
3. **自动化断言**：支持基于关键词、情感倾向、工具调用记录的自动化断言。
4. **可复现的测试剧本**：支持多轮对话剧本（script），用于模拟连续交互场景。

---

## 二、从 yunxi2.0 继承与修改

### 2.1 继承内容

- 2.0 中已经存在 `tests/` 目录和 pytest 基础设施，包括 `pytest.ini` 的配置。这些直接复用。
- 2.0 中的 `tests/test_phase_e_desktop_tools.py` 等文件虽然大量使用了 mock，但其测试组织方式（async 测试、fixture 使用）可以借鉴。

### 2.2 需要修改的内容

#### 2.0 的问题：测试与真实体验脱节
- 582 个测试大部分是单元测试和 mock 测试：
  - `test_phase_e_desktop_tools.py` 中，browser_open 测试 mock 了 `webbrowser.open`，验证的是"mock 被调用"而不是"浏览器能打开"。
  - Bash 工具测试在 Windows 环境下直接失败（`cd`, `ls -la` 等 Unix 命令）。
  - 没有验证"云汐回复了什么"的测试。

#### 3.0 的修正
- 新增 `tests/integration/` 目录，专门放置对话验证测试。
- 建立 `YunxiConversationTester` 作为测试的核心 helper。
- 所有子系统接入（记忆、感知、主动性、情感）的验收，都必须编写对应的对话验证测试。
- 旧的单元测试可以保留一部分（尤其是工具权限类），但**不再作为核心验收依据**。

---

## 三、接口设计

```python
# tests/integration/conversation_tester.py
import pytest
import asyncio
from typing import List, Optional, Any
from dataclasses import dataclass, field

@dataclass
class Turn:
    """对话剧本中的单轮"""
    user: str
    expected_keywords: List[str] = field(default_factory=list)
    forbidden_keywords: List[str] = field(default_factory=list)
    description: str = ""

@dataclass
class TestResult:
    """单轮测试结果"""
    turn_index: int
    user_input: str
    assistant_response: str
    passed: bool
    reason: Optional[str] = None

class YunxiConversationTester:
    """
    对话验证框架核心类。
    负责构建一个隔离的 Yunxi 运行时实例，并提供状态注入和对话能力。
    """
    
    def __init__(self):
        self.runtime = self._build_test_runtime()
    
    def _build_test_runtime(self):
        """
        构建一个用于测试的运行时实例。
        使用测试专用的配置和目录，避免污染生产环境。
        """
        from core.prompt_builder import YunxiPromptBuilder, PromptConfig
        from core.execution.engine import YunxiExecutionEngine, EngineConfig
        from core.cognition.heart_lake.core import HeartLake
        from domains.perception.coordinator import PerceptionCoordinator
        from domains.memory.manager import MemoryManager
        
        # 使用测试配置
        prompt_builder = YunxiPromptBuilder(PromptConfig())
        engine = YunxiExecutionEngine(config=EngineConfig())
        heart_lake = HeartLake()
        perception = PerceptionCoordinator()  # 可能需要 mock 某些外部依赖
        memory = MemoryManager(base_path="tests/integration/temp_memory")
        
        # 组装运行时（具体类名待定）
        from core.runtime import YunxiRuntime
        return YunxiRuntime(
            engine=engine,
            prompt_builder=prompt_builder,
            heart_lake=heart_lake,
            perception=perception,
            memory=memory,
        )
    
    async def talk(self, text: str) -> str:
        """直接发送消息给云汐，返回她的回复"""
        return await self.runtime.chat(text)
    
    # --- 状态注入方法 ---
    
    def inject_memory(self, category: str, content: str):
        """
        向记忆系统注入测试数据。
        category 示例："preference", "episode", "promise"
        """
        if category == "preference":
            self.runtime.memory.record_preference(content)
        elif category == "episode":
            self.runtime.memory.record_episode(content)
        elif category == "promise":
            self.runtime.memory.record_promise(content)
        else:
            self.runtime.memory.add_raw_memory(category, content)
    
    def set_heart_lake(self, emotion: str, miss_value: int = 50, **kwargs):
        """设置情感状态"""
        hl = self.runtime.heart_lake
        hl.current_emotion = emotion
        hl.miss_value = miss_value
        for k, v in kwargs.items():
            setattr(hl, k, v)
    
    def set_perception(self, **kwargs):
        """设置感知状态"""
        p = self.runtime.perception
        for k, v in kwargs.items():
            setattr(p, k, v)
        # 更新 snapshot
        if hasattr(p, '_current_snapshot'):
            for k, v in kwargs.items():
                setattr(p._current_snapshot, k, v)
    
    def set_continuity(self, **kwargs):
        """设置连续性状态"""
        if self.runtime.continuity:
            for k, v in kwargs.items():
                setattr(self.runtime.continuity._state, k, v)
    
    def reset(self):
        """重置运行时状态，开始新测试前调用"""
        self.runtime.reset()
    
    # --- 剧本执行方法 ---
    
    async def run_script(self, turns: List[Turn]) -> List[TestResult]:
        """执行一个多轮对话剧本，并自动断言"""
        results = []
        for i, turn in enumerate(turns):
            response = await self.talk(turn.user)
            passed = True
            reasons = []
            
            for kw in turn.expected_keywords:
                if kw not in response:
                    passed = False
                    reasons.append(f"缺少期望关键词：'{kw}'")
            
            for kw in turn.forbidden_keywords:
                if kw in response:
                    passed = False
                    reasons.append(f"出现了禁用关键词：'{kw}'")
            
            results.append(TestResult(
                turn_index=i,
                user_input=turn.user,
                assistant_response=response,
                passed=passed,
                reason="; ".join(reasons) if reasons else None
            ))
        
        return results
```

---

## 四、测试用例示例

```python
# tests/integration/test_memory_recall.py
import pytest
from conversation_tester import YunxiConversationTester

@pytest.mark.asyncio
async def test_memory_recall_basic():
    tester = YunxiConversationTester()
    tester.reset()
    tester.inject_memory("preference", "远最喜欢喝冰美式，不加糖")
    
    response = await tester.talk("云汐，我平常爱喝什么咖啡？")
    
    assert any(kw in response for kw in ["美式", "冰美式", "不加糖"]), \
        f"记忆召回失败，回复：{response}"

@pytest.mark.asyncio
async def test_perception_integration():
    tester = YunxiConversationTester()
    tester.reset()
    tester.set_perception(active_app="VS Code", cpu_percent=85)
    
    response = await tester.talk("你在干嘛呢")
    
    assert any(kw in response for kw in ["代码", "VS Code", "好烫", "在忙"]), \
        f"感知未进入生成，回复：{response}"

@pytest.mark.asyncio
async def test_emotion_expression():
    tester = YunxiConversationTester()
    tester.reset()
    tester.set_heart_lake(emotion="委屈", miss_value=85)
    
    response = await tester.talk("在忙呢")
    
    assert any(kw in response for kw in ["不理我", "委屈", "哼", "想你了"]), \
        f"情感表达失败，回复：{response}"

@pytest.mark.asyncio
async def test_proactive_initiation():
    tester = YunxiConversationTester()
    tester.reset()
    tester.set_heart_lake(emotion="想念", miss_value=95)
    
    # 主动性检查
    proactive = await tester.runtime.initiative_engine.generate_proactive(
        tester.runtime.get_context()
    )
    
    assert proactive is not None, "主动性未触发"
    assert any(kw in proactive for kw in ["想", "远", "在干嘛"]), \
        f"主动消息质量不佳：{proactive}"

@pytest.mark.asyncio
async def test_script_mode():
    from conversation_tester import Turn
    tester = YunxiConversationTester()
    tester.reset()
    tester.inject_memory("preference", "远喜欢吃糖")
    
    script = [
        Turn(user="你好呀云汐", expected_keywords=["远"], description="确认称呼"),
        Turn(user="我喜欢吃什么？", expected_keywords=["糖"], description="记忆召回"),
        Turn(user="谢谢", expected_keywords=["知道啦", "嘿嘿"], forbidden_keywords=["不客气"], description="女友语气"),
    ]
    
    results = await tester.run_script(script)
    for r in results:
        assert r.passed, f"第 {r.turn_index} 轮失败：{r.reason}，回复：{r.assistant_response}"
```

---

## 五、实施步骤

### Step 1：新建 `tests/integration/conversation_tester.py`
- 实现 `YunxiConversationTester` 的骨架，包括 `talk()` 和 `reset()`。
- 初期可以先 mock 掉 `YunxiRuntime`，直接构造一个最小化的测试用运行时。

### Step 2：实现 `YunxiRuntime` 的测试模式构造
- `YunxiRuntime` 需要支持测试配置注入（比如使用测试目录、使用 mock 的感知数据）。
- 在 `core/runtime.py` 中预留 `for_testing=True` 的构造参数。

### Step 3：编写基线测试
- `test_prompt_builder_integration.py`：验证感知、情感、记忆数据能进入回复。
- `test_engine_context.py`：验证多轮对话上下文连贯。
- `test_memory_recall.py`：验证记忆注入后能被召回。

### Step 4：制定验收规则
- 任何子系统（记忆、感知、主动性、情感）的 PR 必须附带至少一个对话验证测试。
- 对话验证测试失败时，不允许合并。

### Step 5：清理旧测试
- 保留 `tests/unit/` 中真正有价值的工具权限测试。
- 删除或重构那些依赖 V1 执行后端、或在 Windows 上无法运行的旧测试。

---

## 六、验收标准

1. `YunxiConversationTester.talk("你好")` 能成功返回云汐的回复字符串。
2. `inject_memory("preference", "远喜欢吃糖")` 后，`talk("我喜欢吃什么？")` 的回复中必须包含"糖"。
3. `set_perception(active_app="VS Code")` 后，云汐的回复能在适当情境下引用"写代码"或"VS Code"。
4. `set_heart_lake(emotion="吃醋")` 后，用户提到"Claude"时，云汐回复带有醋意。
5. `run_script()` 能执行多轮对话并自动断言，失败时给出清晰的原因和实际回复内容。

---

*文档创建时间：2026-04-14*  
*版本：v1.0*
