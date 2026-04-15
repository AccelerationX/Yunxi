"""Desktop MCP Server。

提供基于 UIA 和视觉断言的桌面操作工具，包括：
- 截图
- 剪贴板读写
- 桌面通知
- 应用启动（带视觉断言）
- 窗口聚焦
"""

from mcp.server.fastmcp import FastMCP

from core.tools.desktop.uia_driver import UIADriver
from core.tools.desktop.visual_assertion import VisualAssertion

mcp = FastMCP("yunxi-desktop")


@mcp.tool()
def screenshot_capture(save_path: str) -> str:
    """截取全屏并保存到指定路径。"""
    from PIL import ImageGrab

    img = ImageGrab.grab(all_screens=True)
    img.save(save_path)
    return f"截图已保存至 {save_path}"


@mcp.tool()
def clipboard_read() -> str:
    """读取系统剪贴板内容。"""
    import pyperclip

    try:
        text = pyperclip.paste()
        return text if text else "[剪贴板为空]"
    except Exception as exc:
        return f"[读取剪贴板失败：{exc}]"


@mcp.tool()
def clipboard_write(text: str) -> str:
    """将文本写入系统剪贴板。"""
    import pyperclip

    try:
        pyperclip.copy(text)
        return "已写入剪贴板"
    except Exception as exc:
        return f"[写入剪贴板失败：{exc}]"


@mcp.tool()
def desktop_notify(title: str, message: str) -> str:
    """发送桌面通知（Windows Toast）。"""
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(title, message, duration=5)
        return "通知已发送"
    except ImportError:
        return "[错误：未安装 win10toast，无法发送通知]"
    except Exception as exc:
        return f"[发送通知失败：{exc}]"


@mcp.tool()
def app_launch_ui(app_name: str) -> str:
    """
    启动应用程序，并通过视觉断言验证屏幕是否发生变化。

    Args:
        app_name: 应用名（如 "notepad", "calc"）。
    """
    import time

    driver = UIADriver()
    assertion = VisualAssertion()

    before = assertion.capture()
    result = driver.launch_application(app_name)
    time.sleep(1.5)
    after = assertion.capture()

    changed = assertion.pixel_diff(before, after, threshold=0.02)
    if not changed:
        return (
            f"已尝试启动 {app_name}（路径：{result['resolved_path'] or 'shell'}），"
            f"但屏幕未检测到显著变化，可能启动失败"
        )

    return f"成功启动 {app_name}"


@mcp.tool()
def window_focus_ui(window_title_keyword: str) -> str:
    """
    基于 UIA 精准聚焦窗口。

    Args:
        window_title_keyword: 窗口标题包含的关键词。
    """
    driver = UIADriver()
    window = driver.find_window_by_title(window_title_keyword)
    if window is None:
        return f"未找到标题包含 '{window_title_keyword}' 的窗口"

    driver.set_foreground(window)
    return f"已聚焦窗口：{window.Name}"


@mcp.tool()
def window_minimize_ui(window_title_keyword: str) -> str:
    """
    最小化指定窗口。

    Args:
        window_title_keyword: 窗口标题包含的关键词。
    """
    driver = UIADriver()
    window = driver.find_window_by_title(window_title_keyword)
    if window is None:
        return f"未找到标题包含 '{window_title_keyword}' 的窗口"

    driver.minimize_window(window)
    return f"已最小化窗口：{window.Name}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
