"""Windows UI Automation 桌面操作驱动器。

借鉴 13_computer_use_agent 的 UIA 控件探测与原子化操作思想，
在 yunxi3.0 内重写，替代脆弱的 ctypes 硬编码实现。
"""

import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

import uiautomation as auto


class UIADriver:
    """
    基于 Windows UI Automation 的桌面操作驱动器。

    提供窗口查找、控件探测、应用启动、原子化点击等能力。
    """

    def find_window_by_title(self, keyword: str) -> Optional[auto.WindowControl]:
        """
        按标题关键词查找顶层窗口。

        Args:
            keyword: 窗口标题包含的关键词，大小写不敏感。

        Returns:
            匹配到的 WindowControl，未找到时返回 None。
        """
        desktop = auto.GetRootControl()
        for window in desktop.GetChildren():
            if isinstance(window, auto.WindowControl):
                if keyword.lower() in window.Name.lower():
                    return window
        return None

    def find_control_by_name(
        self,
        window: auto.WindowControl,
        name: str,
        control_type: Optional[str] = None,
    ) -> Optional[auto.Control]:
        """
        在指定窗口内按名称查找控件。

        Args:
            window: 目标窗口。
            name: 控件名称（控件的 Name 属性）。
            control_type: 可选的控件类型过滤（如 "Button", "Edit"）。

        Returns:
            匹配到的控件，未找到时返回 None。
        """
        for ctrl, _depth in auto.WalkControl(window, maxDepth=5):
            if name.lower() not in ctrl.Name.lower():
                continue
            if control_type is not None:
                if ctrl.ControlTypeName != control_type:
                    continue
            return ctrl
        return None

    def list_interactive_controls(
        self,
        window: auto.WindowControl,
        max_depth: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        列出窗口内所有可交互控件的信息。

        Args:
            window: 目标窗口。
            max_depth: 遍历深度限制。

        Returns:
            控件信息字典列表，每个字典包含 name, control_type, automation_id, rect。
        """
        controls: List[Dict[str, Any]] = []
        for ctrl, _depth in auto.WalkControl(window, maxDepth=max_depth):
            if not (hasattr(ctrl, "Click") or hasattr(ctrl, "SendKeys")):
                continue
            rect = ctrl.BoundingRectangle
            controls.append({
                "name": ctrl.Name,
                "control_type": ctrl.ControlTypeName,
                "automation_id": getattr(ctrl, "AutomationId", ""),
                "x": rect.left if rect else 0,
                "y": rect.top if rect else 0,
                "width": rect.width() if rect else 0,
                "height": rect.height() if rect else 0,
            })
        return controls

    def launch_application(self, app_name: str) -> Dict[str, Any]:
        """
        启动应用程序。

        优先在 PATH 中查找可执行文件；找不到时尝试通过 shell 启动。

        Args:
            app_name: 应用名或可执行文件名（如 "notepad", "code"）。

        Returns:
            包含 launched 和 resolved_path 的字典。
        """
        resolved = shutil.which(app_name)
        if resolved:
            subprocess.Popen([resolved], shell=False)
        else:
            subprocess.Popen([app_name], shell=True)

        return {
            "launched": app_name,
            "resolved_path": resolved,
        }

    def set_foreground(self, window: auto.WindowControl) -> None:
        """将窗口设为前台焦点。"""
        window.SetTopmost(True)
        window.SetTopmost(False)
        window.SwitchToThisWindow()

    def minimize_window(self, window: auto.WindowControl) -> None:
        """最小化窗口。"""
        window.Minimize()

    def atomic_click(self, control: auto.Control) -> bool:
        """
        原子化点击：悬停 → 暂停 → 点击 → 暂停。

        通过分解动作减少误触概率。

        Args:
            control: 目标控件。

        Returns:
            点击是否成功执行。
        """
        import pyautogui

        rect = control.BoundingRectangle
        if rect is None:
            return False

        center_x = rect.left + rect.width() // 2
        center_y = rect.top + rect.height() // 2

        pyautogui.moveTo(center_x, center_y, duration=0.2)
        time.sleep(0.1)
        pyautogui.click(center_x, center_y)
        time.sleep(0.1)
        return True
