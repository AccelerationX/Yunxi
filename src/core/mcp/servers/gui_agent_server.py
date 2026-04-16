"""GUI Agent MCP Server.

This is the yunxi3.0-owned rewrite of the useful parts from
13_computer_use_agent: UIA observation, atomic GUI actions, hotkeys, and macro
storage. Complex visual planning can later plug into gui_run_task without
changing the public tool names.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from core.tools.desktop.uia_driver import UIADriver


mcp = FastMCP("yunxi-gui-agent")


def _macro_dir() -> Path:
    path = Path(os.getenv("YUNXI_GUI_MACRO_DIR", "data/gui_macros"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_macro_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in name)[:80] or "macro"


def _get_window(window_title_keyword: str = ""):
    import uiautomation as uia

    driver = UIADriver()
    if window_title_keyword:
        return driver.find_window_by_title(window_title_keyword)
    return uia.GetForegroundControl()


@mcp.tool()
def gui_observe(window_title_keyword: str = "", max_controls: int = 60) -> str:
    """Observe the foreground window or a named window through UIA."""
    try:
        window = _get_window(window_title_keyword)
        if window is None:
            return f"未找到窗口：{window_title_keyword}"
        driver = UIADriver()
        controls = driver.list_interactive_controls(window)
        rows = [f"窗口：{window.Name} ({window.ControlTypeName})"]
        for idx, item in enumerate(controls[:max_controls], 1):
            rows.append(
                f"{idx}. {item.get('control_type')} name='{item.get('name')}' "
                f"id='{item.get('automation_id')}' "
                f"rect=({item.get('x')},{item.get('y')},{item.get('width')},{item.get('height')})"
            )
        return "\n".join(rows)
    except Exception as exc:
        return f"[GUI 观察失败：{exc}]"


@mcp.tool()
def gui_click(
    control_name: str,
    window_title_keyword: str = "",
    control_type: str = "",
) -> str:
    """Click a UIA control by name in the foreground or named window."""
    try:
        window = _get_window(window_title_keyword)
        if window is None:
            return f"未找到窗口：{window_title_keyword}"
        driver = UIADriver()
        target = driver.find_control_by_name(
            window,
            control_name,
            control_type=control_type or None,
        )
        if target is None:
            return f"未找到控件：{control_name}"
        ok = driver.atomic_click(target)
        return f"已点击控件：{target.Name}" if ok else f"[点击失败：控件没有有效坐标：{control_name}]"
    except Exception as exc:
        return f"[GUI 点击失败：{exc}]"


@mcp.tool()
def gui_type(text: str) -> str:
    """Type text into the current focused UI field."""
    if _send_keys_with_powershell(text):
        return "已向当前焦点输入文本"
    return "[GUI 输入失败：Windows SendKeys 启动失败]"


@mcp.tool()
def gui_hotkey(keys: str) -> str:
    """Press a hotkey, using '+' or ',' to separate keys."""
    try:
        import pyautogui

        parts = [part.strip() for part in re.split(r"[+,]", keys) if part.strip()]
        if not parts:
            return "[热键失败：没有有效按键]"
        pyautogui.hotkey(*parts)
        return f"已按下热键：{'+'.join(parts)}"
    except Exception as exc:
        return f"[热键失败：{exc}]"


@mcp.tool()
def gui_run_task(task: str, dry_run: bool = True) -> str:
    """Run a small GUI task or return a dry-run plan for complex tasks."""
    if dry_run:
        return (
            "GUI 任务已解析为安全预演：\n"
            f"- 任务：{task}\n"
            "- 闭环步骤：observe -> plan -> act -> verify -> replan\n"
            "- 可用动作：gui_observe -> gui_click/gui_type/gui_hotkey -> gui_verify_text\n"
            "- 当前未执行真实点击或输入"
        )

    lowered = task.lower()
    try:
        if "notepad" in lowered or "记事本" in task:
            subprocess.Popen(["notepad.exe"], shell=False)
            return "已启动 Notepad，后续可继续观察、输入或保存宏"
        return "GUI 任务入口已收到请求，但当前只自动执行低风险内置任务；复杂任务请拆成 observe/click/type/hotkey。"
    except Exception as exc:
        return f"[GUI 任务执行失败：{exc}]"


@mcp.tool()
def gui_save_macro(
    name: str,
    steps_json: str,
    trigger: str = "",
    window_title_keyword: str = "",
) -> str:
    """Save a GUI macro. steps_json must be a JSON list of action dicts."""
    try:
        steps = json.loads(steps_json)
        if not isinstance(steps, list):
            return "[保存宏失败：steps_json 必须是 JSON list]"
        macro = {
            "name": name,
            "trigger": trigger,
            "window_title_keyword": window_title_keyword,
            "steps": steps,
            "stats": {
                "runs": 0,
                "successes": 0,
                "failures": 0,
                "last_run_at": 0.0,
                "last_failure": "",
            },
        }
        path = _macro_dir() / f"{_safe_macro_name(name)}.json"
        path.write_text(json.dumps(macro, ensure_ascii=False, indent=2), encoding="utf-8")
        return f"GUI 宏已保存：{path}"
    except Exception as exc:
        return f"[保存宏失败：{exc}]"


@mcp.tool()
def gui_list_macros() -> str:
    """List saved GUI macros."""
    rows: list[str] = []
    for path in sorted(_macro_dir().glob("*.json")):
        try:
            macro = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            rows.append(path.stem)
            continue
        stats = macro.get("stats", {}) if isinstance(macro, dict) else {}
        rows.append(
            f"{path.stem}\truns={stats.get('runs', 0)}\t"
            f"success={stats.get('successes', 0)}\tfailure={stats.get('failures', 0)}"
        )
    return "\n".join(rows) if rows else "[暂无 GUI 宏]"


@mcp.tool()
def gui_macro_stats(name: str) -> str:
    """Return stored macro metadata and run statistics."""
    try:
        path = _macro_dir() / f"{_safe_macro_name(name)}.json"
        if not path.exists():
            return f"[宏统计失败：宏不存在：{name}]"
        macro = json.loads(path.read_text(encoding="utf-8"))
        return json.dumps(macro, ensure_ascii=False, indent=2)
    except Exception as exc:
        return f"[宏统计失败：{exc}]"


@mcp.tool()
def gui_run_macro(name: str, params_json: str = "{}", dry_run: bool = True) -> str:
    """Run or preview a saved GUI macro."""
    try:
        path = _macro_dir() / f"{_safe_macro_name(name)}.json"
        if not path.exists():
            return f"[执行宏失败：宏不存在：{name}]"
        macro = json.loads(path.read_text(encoding="utf-8"))
        params = json.loads(params_json or "{}")
        if not isinstance(params, dict):
            return "[执行宏失败：params_json 必须是 JSON object]"
        steps = _render_steps(macro.get("steps", []), params)
        window_title_keyword = str(
            macro.get("window_title_keyword") or params.get("window_title_keyword") or ""
        )
        if window_title_keyword:
            for step in steps:
                step.setdefault("window_title_keyword", window_title_keyword)
        if dry_run:
            return "GUI 宏预演：\n" + json.dumps(steps, ensure_ascii=False, indent=2)
        result = _execute_macro_steps(steps)
        _record_macro_run(path, macro, result)
        return result
    except Exception as exc:
        return f"[执行宏失败：{exc}]"


def _render_steps(steps: list[dict[str, Any]], params: dict[str, Any]) -> list[dict[str, Any]]:
    rendered = []
    for step in steps:
        item = {}
        for key, value in step.items():
            if isinstance(value, str):
                item[key] = value.format(**params)
            else:
                item[key] = value
        rendered.append(item)
    return rendered


def _execute_macro_steps(steps: list[dict[str, Any]]) -> str:
    results = []
    for step in steps:
        action = step.get("action")
        if action == "type":
            results.append(gui_type(str(step.get("text", ""))))
        elif action == "hotkey":
            results.append(gui_hotkey(str(step.get("keys", ""))))
        elif action == "verify_text":
            results.append(
                gui_verify_text(
                    expected_text=str(step.get("expected_text", "")),
                    window_title_keyword=str(step.get("window_title_keyword", "")),
                )
            )
        elif action == "click":
            results.append(
                gui_click(
                    control_name=str(step.get("control_name", "")),
                    window_title_keyword=str(step.get("window_title_keyword", "")),
                    control_type=str(step.get("control_type", "")),
                )
            )
        else:
            results.append(f"[跳过未知宏动作：{action}]")
    return "\n".join(results)


@mcp.tool()
def gui_verify_text(expected_text: str, window_title_keyword: str = "") -> str:
    """Verify that observed UIA text contains expected text."""
    if not expected_text:
        return "[GUI 验证失败：expected_text 不能为空]"
    observed = gui_observe(window_title_keyword=window_title_keyword, max_controls=120)
    if expected_text in observed:
        return f"GUI 验证通过：找到文本 {expected_text}"
    return f"[GUI 验证失败：未找到文本 {expected_text}]"


def _record_macro_run(path: Path, macro: dict[str, Any], result: str) -> None:
    stats = macro.get("stats")
    if not isinstance(stats, dict):
        stats = {}
    failed = "[" in result or "失败" in result or "未找到" in result
    stats["runs"] = int(stats.get("runs", 0)) + 1
    stats["last_run_at"] = time.time()
    if failed:
        stats["failures"] = int(stats.get("failures", 0)) + 1
        stats["last_failure"] = _first_failure_line(result)
    else:
        stats["successes"] = int(stats.get("successes", 0)) + 1
        stats["last_failure"] = ""
    macro["stats"] = stats
    path.write_text(json.dumps(macro, ensure_ascii=False, indent=2), encoding="utf-8")


def _first_failure_line(result: str) -> str:
    for line in result.splitlines():
        if "[" in line or "失败" in line or "未找到" in line:
            return line[:240]
    return ""


def _send_keys_with_powershell(text: str) -> bool:
    """Send text to the current focused control without blocking the MCP process."""
    if not text:
        return True
    escaped = (
        text.replace("'", "''")
        .replace("{", "{{}")
        .replace("}", "{}}")
        .replace("+", "{+}")
        .replace("^", "{^}")
        .replace("%", "{%}")
        .replace("~", "{~}")
        .replace("(", "{(}")
        .replace(")", "{)}")
        .replace("[", "{[}")
        .replace("]", "{]}")
    )
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        f"[System.Windows.Forms.SendKeys]::SendWait('{escaped}')"
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        return True
    except OSError:
        return False


if __name__ == "__main__":
    mcp.run(transport="stdio")
