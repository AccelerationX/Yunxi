# 云汐 3.0 工具层重构设计文档（MCP 全面化 + Computer Use Agent）

> **定位**：将 yunxi2.0 的硬编码工具层升级为基于 MCP 标准的动态工具中枢，桌面操作全面迁移到 UIA + 视觉断言。  
> **核心原则**：所有工具统一通过 MCP Server 暴露，工具链由 DAGPlanner 自动编排，桌面操作由 UIA 精确驱动，视觉断言确保执行可靠性。

---

## 一、设计目标

1. **全面 MCP 化**：所有工具均包装为 FastMCP Server，通过 MCP Client 动态发现与调用。
2. **工具链自动编排**：复杂意图（如"查天气然后截图发给我"）由 `DAGPlanner` 自动分解为最小执行图，而不是依赖 LLM 的隐式推理。
3. **UIA 精确驱动**：桌面工具（窗口控制、应用启动、媒体控制）全面基于 Windows UI Automation 实现，替代脆弱的 `ctypes` 硬编码。
4. **视觉断言闭环**：高风险桌面操作执行前后自动截图对比，失败时触发重试或降级。
5. **安全与审计统一**：引入四级权限模型（READ/WRITE/EXECUTE/NETWORK），所有调用写入 `audit.jsonl`。

---

## 二、研究成果借鉴与重写声明

### 2.1 借鉴 `14_mcp_tool_hub`

**借鉴内容**：
- MCP stdio Client 与 Server 的通信模型
- `SemanticMatcher`（Embedding + Keyword Gate）的工具召回思路
- `DAGPlanner` 基于输入输出依赖生成执行图
- `SecurityManager` 的三级风险策略与用户确认流程
- `AuditLogger` 的 JSONL 审计日志格式

**重写声明**：
- 不在 yunxi3.0 中 import `14_mcp_tool_hub` 的任何文件。
- 在 `yunxi3.0/core/mcp/` 目录下重写 `client.py`、`hub.py`、`planner.py`、`security.py`、`audit_logger.py`，接口和实现会根据 yunxi3.0 的 asyncio 架构重新设计。

### 2.2 借鉴 `13_computer_use_agent`

**借鉴内容**：
- UIA（`uiautomation` 库）控件树探测与精确操作
- 视觉断言（操作前后 `pixel_diff` + 自适应阈值）
- 原子化执行（`hover → pause → click → pause`）
- GUI Macro（成功序列的参数化复用）
- 任务评估器（用 UIA 读取控件内容验证结果）

**重写声明**：
- 不在 yunxi3.0 中 import `13_computer_use_agent` 的任何文件。
- 在 `yunxi3.0/core/tools/desktop/` 目录下重写 `uia_driver.py`、`visual_assertion.py`、`macro_engine.py`、`task_evaluator.py`。

### 2.3 借鉴 `02_llm_agent_security_sandbox`

**借鉴内容**：
- 四级权限模型分类
- 操作审计图谱

**重写声明**：
- 在 `yunxi3.0/core/security/` 目录下重写 `permission_model.py` 和 `risk_classifier.py`，与 MCP SecurityManager 融合。

---

## 三、MCP 工具中枢架构

### 3.1 架构图

```
用户输入 / LLM ToolUse 请求
        ↓
┌───────────────────┐
│   SemanticMatcher │  (Embedding + Keyword Gate)
│   工具语义召回      │
└─────────┬─────────┘
          ↓
┌───────────────────┐
│   ArgumentResolver│  (Regex / LLM / Schema 校验)
│   参数推断与填充    │
└─────────┬─────────┘
          ↓
┌───────────────────┐
│    DAGPlanner     │  (拓扑排序 + 数据流分析)
│   工具链自动编排    │
└─────────┬─────────┘
          ↓
┌───────────────────┐
│   SecurityManager │  (四级权限 + 风险校验 + 用户确认)
│   安全策略校验      │
└─────────┬─────────┘
          ↓
┌───────────────────┐
│    MCP Client     │  (stdio / sse)
│   统一工具调用      │
└─────────┬─────────┘
          ↓
    ┌─────┴─────┬──────────┬──────────┐
    ↓           ↓          ↓          ↓
┌───────┐  ┌───────┐  ┌───────┐  ┌───────┐
│Bash   │  │File   │  │Desktop│  │Browser│
│Server │  │Server │  │Server │  │Server │
└───────┘  └───────┘  └───────┘  └───────┘
    ↓           ↓          ↓          ↓
┌──────────────────────────────────────────┐
│         AuditLogger (audit.jsonl)        │
└──────────────────────────────────────────┘
```

### 3.2 MCP Hub 接口设计

```python
# core/mcp/hub.py
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class ToolCallPlan:
    tool_name: str
    arguments: Dict[str, Any]
    depends_on: List[str]  # 依赖的其他 tool call id
    call_id: str

@dataclass
class ToolChainResult:
    results: List[Dict[str, Any]]
    audit_log_id: str
    security_decisions: List[Dict[str, Any]]

class MCPHub:
    """
    云汐 3.0 的 MCP 工具中枢。
    负责：工具发现 → 语义匹配 → DAG 规划 → 安全校验 → 执行 → 审计。
    """
    def __init__(self, servers: List[str]):
        """
        servers: MCP Server 启动命令列表，如 ["python -m tools.servers.bash", ...]
        """
        self.client = MCPClient()
        self.matcher = SemanticMatcher()
        self.resolver = ArgumentResolver()
        self.planner = DAGPlanner()
        self.security = SecurityManager()
        self.audit = AuditLogger()
        self._servers = servers
        self._tool_cache: Dict[str, Any] = {}
    
    async def initialize(self):
        """启动所有 MCP Server 并完成工具发现"""
        for server_cmd in self._servers:
            await self.client.connect_server(server_cmd)
        tools = await self.client.list_tools()
        self._tool_cache = {t.name: t for t in tools}
        await self.matcher.index_tools(tools)
    
    async def execute_intent(self, intent_text: str, context: Any) -> ToolChainResult:
        """
        从自然语言意图到工具链执行的高级入口。
        用于日常模式中 LLM 不直接输出 tool_calls，而是给出模糊意图的场景。
        """
        # 1. 语义召回
        candidate_tools = await self.matcher.match(intent_text, list(self._tool_cache.values()))
        
        # 2. DAG 规划
        plan = await self.planner.plan(intent_text, candidate_tools)
        
        # 3. 执行工具链
        return await self._execute_plan(plan, context)
    
    async def execute_tool_calls(self, tool_calls: List[Any], context: Any) -> ToolChainResult:
        """
        从 LLM 输出的 tool_calls 直接执行。
        用于 LLM 已经明确知道要调用什么工具的场景。
        """
        plan = []
        for tc in tool_calls:
            plan.append(ToolCallPlan(
                tool_name=tc.name,
                arguments=tc.arguments,
                depends_on=[],
                call_id=tc.id,
            ))
        return await self._execute_plan(plan, context)
    
    async def _execute_plan(self, plan: List[ToolCallPlan], context: Any) -> ToolChainResult:
        """按 DAG 顺序执行，并在每个节点前进行安全校验"""
        results = []
        security_decisions = []
        
        for step in self.planner.topological_sort(plan):
            # 安全校验
            decision = await self.security.evaluate(step, context)
            security_decisions.append(decision.to_dict())
            
            if decision.action == "deny":
                results.append({
                    "call_id": step.call_id,
                    "error": f"安全策略拒绝：{decision.reason}",
                    "is_error": True,
                })
                continue
            
            if decision.action == "ask":
                # 日常模式下：记录为需要用户确认，返回错误信息给 LLM
                # 工厂模式下：如果用户已全局授权，可降级为 allow
                results.append({
                    "call_id": step.call_id,
                    "error": f"需要用户确认：{decision.reason}",
                    "is_error": True,
                })
                continue
            
            # 执行
            try:
                result = await self.client.call_tool(step.tool_name, step.arguments)
                results.append({
                    "call_id": step.call_id,
                    "content": self._normalize_result(result),
                    "is_error": False,
                })
            except Exception as e:
                results.append({
                    "call_id": step.call_id,
                    "error": str(e),
                    "is_error": True,
                })
        
        # 审计
        log_id = await self.audit.record(plan, results, security_decisions)
        
        return ToolChainResult(
            results=results,
            audit_log_id=log_id,
            security_decisions=security_decisions,
        )
    
    def _normalize_result(self, raw: Any) -> str:
        if isinstance(raw, str):
            return raw
        import json
        try:
            return json.dumps(raw, ensure_ascii=False, indent=2)
        except Exception:
            return str(raw)
```

### 3.3 SecurityManager 设计

```python
# core/mcp/security.py
from enum import Enum
from dataclasses import dataclass

class PermissionLevel(Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK = "network"

@dataclass
class SecurityDecision:
    action: str  # allow / ask / deny
    reason: str
    risk_score: float  # 0.0 - 1.0

class SecurityManager:
    """
    借鉴 14_mcp_tool_hub 和 02_llm_agent_security_sandbox 的安全策略思想，
    但在 yunxi3.0 内重写，与 asyncio 和 MCP 协议适配。
    """
    def __init__(self):
        self.tool_permissions: Dict[str, List[PermissionLevel]] = {}
        self.global_policy = {
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
    
    def register_tool(self, tool_name: str, permissions: List[PermissionLevel]):
        self.tool_permissions[tool_name] = permissions
    
    async def evaluate(self, step: ToolCallPlan, context: Any) -> SecurityDecision:
        perms = self.tool_permissions.get(step.tool_name, [PermissionLevel.READ])
        mode = getattr(context, 'mode', 'daily_mode')
        policy = self.global_policy.get(mode, self.global_policy['daily_mode'])
        
        max_risk = 0.0
        blocking_perm = None
        
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
                reason=f"工具 {step.tool_name} 需要 {blocking_perm.value} 权限，当前策略禁止",
                risk_score=max_risk
            )
        elif max_risk >= 0.5:
            return SecurityDecision(
                action="ask",
                reason=f"工具 {step.tool_name} 涉及 {blocking_perm.value} 操作，需要确认",
                risk_score=max_risk
            )
        
        return SecurityDecision(action="allow", reason="通过", risk_score=0.0)
```

### 3.4 AuditLogger 设计

```python
# core/mcp/audit_logger.py
import json
import os
from datetime import datetime

class AuditLogger:
    def __init__(self, log_dir: str = "logs/mcp_audit"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.log_path = os.path.join(log_dir, f"audit_{datetime.now().strftime('%Y%m%d')}.jsonl")
    
    async def record(self, plan, results, security_decisions) -> str:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "plan": [{"tool": p.tool_name, "args": p.arguments, "id": p.call_id} for p in plan],
            "results": results,
            "security": security_decisions,
        }
        log_id = f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        entry["log_id"] = log_id
        
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        
        return log_id
```

---

## 四、MCP Server 清单（日常模式）

### 4.1 Server 列表

| Server | 工具 | 权限级别 | 说明 |
|--------|------|---------|------|
| `yunxi_mcp_filesystem` | `file_read`, `file_write`, `file_append`, `file_copy`, `file_move`, `list_dir`, `glob`, `grep`, `document_read` | READ + WRITE | 文件、目录和常见文档读取/整理。日常模式默认限制在允许根目录内，写入/移动/复制需要确认。 |
| `yunxi_mcp_desktop` | `desktop_notify`, `screenshot_capture`, `clipboard_read`, `clipboard_write`, `app_launch_ui`, `window_focus_ui`, `window_minimize_ui`, `media_control_ui` | READ + WRITE + EXECUTE | 桌面操作（基于 UIA）。 |
| `yunxi_mcp_browser` | `browser_open`, `browser_search`, `web_page_read`, `browser_extract_links`, `browser_click`, `browser_type` | READ + NETWORK + EXECUTE | 浏览器打开、搜索、网页读取、链接提取和基础页面操作。稳定路径优先使用 URL/HTML 解析；复杂网页自动化后续接 Playwright。 |
| `yunxi_mcp_gui_agent` | `gui_observe`, `gui_click`, `gui_type`, `gui_hotkey`, `gui_run_task`, `gui_save_macro`, `gui_list_macros`, `gui_run_macro` | READ + WRITE + EXECUTE | 参考 `13_computer_use_agent` 重写的 GUI Agent 能力：观察、规划、原子操作、验证、宏记忆。作为浏览器/文件工具无法覆盖时的 fallback。 |
| `yunxi_mcp_bash` | `bash_execute` | READ + EXECUTE | 工厂模式优先。日常模式默认不启用或强制确认，避免把云汐变成裸 shell 代理。 |

### 4.1.1 阶段 6：住在电脑里的完整电脑能力

阶段 6 的目标不是简单堆工具，而是让云汐拥有“能看见电脑、理解文件、操作浏览器、处理文档、必要时接管 GUI”的完整能力，同时保留女友日常模式的安全边界和人格表达。

必须补齐的能力：

1. **浏览器能力**
   - 打开 URL、打开搜索结果页、读取网页正文、提取链接。
   - 对简单网页支持点击和输入；对复杂网页后续接入 Playwright，避免靠坐标盲操作。
   - 典型场景：查资料、打开你给的链接、阅读网页后总结、填写简单表单。

2. **文件与文件夹能力**
   - 列目录、读文件、写文件、追加、复制、移动、glob、grep。
   - 日常模式默认启用允许根目录；跨根目录、覆盖、移动、写入必须走确认。
   - 典型场景：帮你找文件、整理资料、把聊天中确定的内容写入 Markdown。

3. **文档处理能力**
   - Markdown、txt、json、csv、py 等纯文本文件直接读写。
   - docx 使用标准 zip/xml 解析正文；xlsx 使用 zip/xml 读取工作表文本；pdf 在可用时使用本地 PDF 解析库，否则返回明确降级。
   - 典型场景：读取需求文档、总结论文/报告、整理表格内容、生成草稿。

4. **GUI Agent 能力**
   - UIA 控件树观察、窗口内控件枚举、按控件名点击、当前焦点输入、热键。
   - 每一步执行后保留验证入口；成功流程可保存为 GUI Macro。
   - 典型场景：操作没有 API 的 Windows 软件、跨应用流程、需要看屏幕后再执行的任务。

5. **工具技能学习**
   - MCP 审计日志和 GUI Macro 进入 SkillLibrary。
   - 重复成功的工具链沉淀为可复用技能；失败案例进入 FailureReplay，提醒云汐避坑。

6. **安全与确认**
   - READ 默认允许。
   - WRITE / EXECUTE 默认 pending confirmation。
   - NETWORK 默认允许读取，但涉及登录、提交、下载、上传、支付、删除、覆盖时必须确认。
   - GUI Agent 的 `gui_click`、`gui_type`、`gui_hotkey`、`gui_run_task` 默认需要确认。

阶段 6 完成后，才进入飞书日常模式浸泡测试。浸泡测试必须覆盖：飞书聊天、主动消息、工具确认、浏览器读取、文件/文档读写、GUI fallback、重启后记忆连续性。

### 4.2 关键 Server 示例：`yunxi_mcp_desktop`

```python
# core/mcp/servers/desktop_server.py
from mcp.server.fastmcp import FastMCP
from core.tools.desktop.uia_driver import UIADriver
from core.tools.desktop.visual_assertion import VisualAssertion

mcp = FastMCP("yunxi-desktop")

@mcp.tool()
def app_launch_ui(app_name: str) -> str:
    """基于 UIA 启动应用并验证窗口是否出现"""
    driver = UIADriver()
    result = driver.launch_application(app_name)
    
    # 视觉断言
    assertion = VisualAssertion()
    before = assertion.capture()
    # 等待窗口出现
    import time
    time.sleep(1.0)
    after = assertion.capture()
    changed = assertion.pixel_diff(before, after, threshold=0.02)
    
    if not changed:
        return f"已尝试启动 {app_name}，但屏幕未检测到变化，可能启动失败"
    return f"成功启动 {app_name}"

@mcp.tool()
def window_focus_ui(window_title_keyword: str) -> str:
    """基于 UIA 精准聚焦窗口，而不是盲按坐标"""
    driver = UIADriver()
    window = driver.find_window_by_title(window_title_keyword)
    if not window:
        return f"未找到标题包含 '{window_title_keyword}' 的窗口"
    driver.set_foreground(window)
    return f"已聚焦窗口：{window.Name}"

@mcp.tool()
def screenshot_capture(save_path: str) -> str:
    """截取屏幕并保存"""
    from PIL import ImageGrab
    img = ImageGrab.grab(all_screens=True)
    img.save(save_path)
    return f"截图已保存至 {save_path}"

@mcp.tool()
def clipboard_read() -> str:
    """读取系统剪贴板（使用 pyperclip）"""
    import pyperclip
    try:
        text = pyperclip.paste()
        return text or "[剪贴板为空]"
    except Exception as e:
        return f"[读取失败：{e}]"

@mcp.tool()
def clipboard_write(text: str) -> str:
    """写入系统剪贴板"""
    import pyperclip
    try:
        pyperclip.copy(text)
        return "已写入剪贴板"
    except Exception as e:
        return f"[写入失败：{e}]"

@mcp.tool()
def desktop_notify(title: str, message: str) -> str:
    """发送桌面通知"""
    from win10toast import ToastNotifier
    toaster = ToastNotifier()
    toaster.show_toast(title, message, duration=5)
    return "通知已发送"

if __name__ == "__main__":
    mcp.run(transport='stdio')
```

---

## 五、Computer Use Agent 桌面工具模块

### 5.1 UIA 驱动器

```python
# core/tools/desktop/uia_driver.py
import uiautomation as auto
from typing import Optional, List, Dict, Any

class UIADriver:
    """
    基于 Windows UI Automation 的桌面操作驱动器。
    从 13_computer_use_agent 的研究成果中借鉴思路，在 yunxi3.0 内重写。
    """
    def find_window_by_title(self, keyword: str) -> Optional[auto.WindowControl]:
        """按标题关键词查找顶层窗口"""
        desktop = auto.GetRootControl()
        for window in desktop.GetChildren():
            if isinstance(window, auto.WindowControl):
                if keyword.lower() in window.Name.lower():
                    return window
        return None
    
    def list_interactive_controls(self, window: auto.WindowControl) -> List[Dict[str, Any]]:
        """列出窗口内所有可交互控件"""
        controls = []
        for ctrl, depth in auto.WalkControl(window, maxDepth=5):
            if hasattr(ctrl, 'Click') or hasattr(ctrl, 'SendKeys'):
                rect = ctrl.BoundingRectangle
                controls.append({
                    "name": ctrl.Name,
                    "control_type": ctrl.ControlTypeName,
                    "automation_id": getattr(ctrl, 'AutomationId', ''),
                    "x": rect.left if rect else 0,
                    "y": rect.top if rect else 0,
                    "width": rect.width() if rect else 0,
                    "height": rect.height() if rect else 0,
                })
        return controls
    
    def launch_application(self, app_name: str) -> Dict[str, Any]:
        """启动应用并返回启动结果"""
        import subprocess
        import shutil
        
        resolved = shutil.which(app_name)
        if resolved:
            subprocess.Popen([resolved], shell=False)
        else:
            subprocess.Popen([app_name], shell=True)
        
        return {"launched": app_name, "resolved_path": resolved}
    
    def set_foreground(self, window: auto.WindowControl):
        """将窗口设为前台"""
        window.SetTopmost(True)
        window.SetTopmost(False)
        window.SwitchToThisWindow()
    
    def atomic_click(self, control: auto.Control) -> bool:
        """
        原子化点击：hover → pause → click → pause。
        借鉴 13_computer_use_agent 的原子化执行思想。
        """
        import time
        import pyautogui
        rect = control.BoundingRectangle
        if not rect:
            return False
        
        center_x = rect.left + rect.width() // 2
        center_y = rect.top + rect.height() // 2
        
        pyautogui.moveTo(center_x, center_y, duration=0.2)
        time.sleep(0.1)
        pyautogui.click(center_x, center_y)
        time.sleep(0.1)
        return True
```

### 5.2 视觉断言模块

```python
# core/tools/desktop/visual_assertion.py
import cv2
import numpy as np
from PIL import ImageGrab
from typing import Tuple

class VisualAssertion:
    """
    操作前后的视觉断言模块。
    借鉴 13_computer_use_agent 的视觉验证思想，在 yunxi3.0 内重写。
    """
    def capture(self) -> np.ndarray:
        """截取全屏并转为 OpenCV 格式"""
        pil_img = ImageGrab.grab(all_screens=True)
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    
    def pixel_diff(self, before: np.ndarray, after: np.ndarray, threshold: float = 0.02) -> bool:
        """
        计算两张截图的像素差异比例。
        threshold: 差异像素占比阈值，超过则判定为"有变化"。
        """
        if before.shape != after.shape:
            # 分辨率变化，直接判定为有变化
            return True
        
        diff = cv2.absdiff(before, after)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
        
        changed_pixels = np.count_nonzero(thresh)
        total_pixels = thresh.size
        ratio = changed_pixels / total_pixels
        
        return ratio > threshold
    
    def mse(self, before: np.ndarray, after: np.ndarray) -> float:
        """均方误差，用于更细粒度的变化量评估"""
        if before.shape != after.shape:
            return float('inf')
        err = np.sum((before.astype("float") - after.astype("float")) ** 2)
        return err / float(before.size)
```

### 5.3 GUI Macro 引擎

```python
# core/tools/desktop/macro_engine.py
import json
import os
from typing import List, Dict, Any

class MacroEngine:
    """
    GUI 宏执行引擎。
    将成功的 GUI 操作序列保存为可复用的参数化宏。
    借鉴 13_computer_use_agent 的技能记忆思想。
    """
    def __init__(self, macro_dir: str = "data/gui_macros"):
        self.macro_dir = macro_dir
        os.makedirs(macro_dir, exist_ok=True)
    
    def save_macro(self, name: str, steps: List[Dict[str, Any]], trigger_patterns: List[str]):
        """保存一个 GUI 宏"""
        path = os.path.join(self.macro_dir, f"{name}.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({
                "name": name,
                "trigger_patterns": trigger_patterns,
                "steps": steps,
            }, f, ensure_ascii=False, indent=2)
    
    def load_macro(self, name: str) -> Dict[str, Any]:
        path = os.path.join(self.macro_dir, f"{name}.json")
        if not os.path.exists(path):
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def execute_macro(self, name: str, params: Dict[str, str]) -> List[str]:
        """执行宏，并用 params 填充模板变量"""
        macro = self.load_macro(name)
        if not macro:
            return [f"宏 {name} 不存在"]
        
        results = []
        for step in macro.get("steps", []):
            action = step["action"]
            # 参数化替换
            arguments = {k: v.format(**params) for k, v in step.get("args", {}).items()}
            results.append(f"执行 {action}({arguments})")
            # 实际执行由调用方通过 MCP Hub 完成
        return results
```

---

## 六、DAGPlanner 设计

```python
# core/mcp/planner.py
from typing import List, Dict, Any
import networkx as nx

class DAGPlanner:
    """
    工具链 DAG 规划器。
    借鉴 14_mcp_tool_hub 的 DAG 编排思想，在 yunxi3.0 内重写。
    """
    def __init__(self):
        # 定义工具间的隐式依赖关系
        self.implicit_deps = {
            "screenshot_capture": [],  # 无依赖
            "clipboard_write": [],
            "browser_search": [],
            "web_page_read": ["browser_search", "browser_open"],
            "window_focus_ui": [],
            "app_launch_ui": [],
        }
    
    async def plan(self, intent_text: str, candidate_tools: List[Any]) -> List[Any]:
        """
        根据意图和候选工具生成执行计划。
        当前版本采用简化策略：按隐式依赖排序，生成串行或并行计划。
        """
        G = nx.DiGraph()
        tool_names = [t.name for t in candidate_tools]
        
        for name in tool_names:
            G.add_node(name)
        
        for name in tool_names:
            deps = self.implicit_deps.get(name, [])
            for dep in deps:
                if dep in tool_names:
                    G.add_edge(dep, name)
        
        if not nx.is_directed_acyclic_graph(G):
            # 如果有环，退化为串行执行
            return list(candidate_tools)
        
        ordered = list(nx.topological_sort(G))
        ordered_tools = [next(t for t in candidate_tools if t.name == name) for name in ordered]
        return ordered_tools
    
    def topological_sort(self, plan: List[Any]) -> List[Any]:
        """对已有计划进行拓扑排序"""
        G = nx.DiGraph()
        for step in plan:
            G.add_node(step.call_id)
        for step in plan:
            for dep in step.depends_on:
                G.add_edge(dep, step.call_id)
        
        ordered_ids = list(nx.topological_sort(G))
        id_map = {step.call_id: step for step in plan}
        return [id_map[iid] for iid in ordered_ids]
```

---

## 七、执行层适配（YunxiExecutionEngine 与 MCP Hub 的交互）

```python
# core/execution/engine.py（MCP 适配部分）
class YunxiExecutionEngine:
    def __init__(self, llm, mcp_hub: MCPHub, config: Optional[EngineConfig] = None):
        self.llm = llm
        self.mcp_hub = mcp_hub
        self.config = config or EngineConfig()
        self.context = ConversationContext(limit=self.config.recent_message_limit)
    
    async def respond(self, user_input: str, system_prompt: str) -> ExecutionResult:
        self.context.add_user_message(user_input)
        
        try:
            for turn in range(self.config.max_turns):
                messages = self.context.get_messages()
                
                # 获取可用工具描述（用于 LLM 的 function calling）
                available_tools = await self.mcp_hub.client.get_tool_descriptions_for_llm()
                
                response = await self.llm.complete(
                    system=system_prompt,
                    messages=messages,
                    tools=available_tools if self.config.enable_tool_use else None
                )
                
                tool_calls = getattr(response, 'tool_calls', None) or []
                
                if not tool_calls:
                    self.context.add_assistant_message(response.content or "")
                    return ExecutionResult(content=response.content or "")
                
                # 通过 MCP Hub 执行工具链
                # 构建 RuntimeContext 用于安全策略判断
                runtime_context = SimpleNamespace(mode="daily_mode")
                chain_result = await self.mcp_hub.execute_tool_calls(tool_calls, runtime_context)
                
                # 将 tool results 加入对话上下文
                self._add_tool_results_to_context(tool_calls, chain_result.results)
            
            return ExecutionResult(
                content="[尝试使用工具多次仍未完成]",
                error="max_turns_exceeded"
            )
        except Exception as e:
            return ExecutionResult(content=f"[错误：{e}]", error=str(e))
    
    def _add_tool_results_to_context(self, tool_calls, results):
        from core.types.message_types import AssistantMessage, ToolUseBlockData
        from core.types.message_types import ToolResultContentBlock, UserMessage
        
        tool_use_blocks = []
        for tc in tool_calls:
            tool_use_blocks.append(ToolUseBlockData(
                id=tc.id, name=tc.name, input=tc.arguments
            ))
        self.context.messages.append(AssistantMessage(content=tool_use_blocks))
        
        result_blocks = []
        for r in results:
            result_blocks.append(ToolResultContentBlock(
                tool_use_id=r["call_id"],
                content=r.get("content") or r.get("error", ""),
                is_error=r.get("is_error", False)
            ))
        self.context.messages.append(UserMessage(content=result_blocks))
```

---

## 八、实施步骤

### Step 1：建立 `core/mcp/` 目录结构
- `client.py`：基于官方 `mcp` 库的 stdio Client 封装
- `hub.py`：`MCPHub` 主类
- `planner.py`：`DAGPlanner`
- `security.py`：`SecurityManager`
- `audit_logger.py`：`AuditLogger`
- `servers/`：各 FastMCP Server 实现

### Step 2：建立 `core/tools/desktop/` 目录结构
- `uia_driver.py`：UIA 驱动
- `visual_assertion.py`：视觉断言
- `macro_engine.py`：GUI Macro
- `task_evaluator.py`：UIA 任务评估器

### Step 3：建立 `core/security/` 目录结构
- `permission_model.py`：四级权限模型
- `risk_classifier.py`：风险分类器

### Step 4：重写核心 MCP Server
- `desktop_server.py`（优先级最高）
- `filesystem_server.py`
- `bash_server.py`
- `browser_server.py`

### Step 5：修改 `YunxiExecutionEngine`
- 构造函数改为接收 `MCPHub` 而非直接接收工具字典
- `respond()` 方法通过 `mcp_hub.execute_tool_calls()` 执行工具

### Step 6：修改 `apps/daemon/main.py`
- 初始化 `MCPHub`，注册所有 Server
- 删除旧的硬编码工具注册逻辑

### Step 7：安装依赖并测试
- `pip install mcp fastmcp pyperclip uiautomation opencv-python Pillow`
- 通过 `ConversationTester` 验证每个 MCP 工具的真实可用性

---

## 九、验收标准

1. `MCPHub.initialize()` 能成功启动所有 MCP Server 并发现工具列表。
2. 用户说"帮我截图"时，`SemanticMatcher` 能召回 `screenshot_capture`，`DAGPlanner` 生成单节点计划，`SecurityManager` 判定为 `allow`，最终成功执行并返回保存路径。
3. `window_focus_ui("记事本")` 能基于 UIA 精准找到记事本窗口并聚焦，而不是对坐标盲操作。
4. `app_launch_ui("notepad")` 执行前后触发视觉断言，屏幕变化比例 > 2% 判定为成功启动。
5. 高风险操作（如 `bash_execute rm -rf`）被 `SecurityManager` 判定为 `ask` 或 `deny`，不会直接执行。
6. 所有工具调用记录写入 `logs/mcp_audit/audit_YYYYMMDD.jsonl`。
7. 通过 `ConversationTester` 测试：连续调用多个工具（如启动记事本 → 写入剪贴板 → 截图）能正确串联执行。

---

*文档创建时间：2026-04-14*  
*最后更新时间：2026-04-16*
*版本：v2.1*
