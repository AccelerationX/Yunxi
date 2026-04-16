"""Direct daily-mode validation for extended tool servers.

This mirrors the Feishu-free flow used for Desktop MCP validation: Yunxi asks
for confirmation on WRITE/EXECUTE tools, then the test simulates the user's
"确认" reply and checks the real tool result.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio

from core.execution.engine import EngineConfig, YunxiExecutionEngine
from core.mcp import AuditLogger, DAGPlanner, MCPClient, MCPHub, SecurityManager
from core.mcp.security import PermissionLevel
from core.types.message_types import ToolResultContentBlock, UserMessage


pytestmark = pytest.mark.desktop_mcp


@dataclass
class FakeResponse:
    content: str = ""
    tool_calls: list[Any] | None = None


class OneToolLLM:
    def __init__(self, tool_name: str, arguments: dict[str, Any]) -> None:
        self.tool_name = tool_name
        self.arguments = arguments

    async def complete(self, *args, **kwargs) -> FakeResponse:
        return FakeResponse(
            tool_calls=[
                SimpleNamespace(
                    id=f"call_{self.tool_name}",
                    name=self.tool_name,
                    arguments=self.arguments,
                )
            ]
        )


class FakeMemory:
    async def try_skill(self, user_input: str):
        return None

    def record_experience(self, **kwargs) -> None:
        return None


@pytest_asyncio.fixture
async def extended_hub(tmp_path):
    client = MCPClient(timeout_seconds=45.0)
    planner = DAGPlanner()
    security = SecurityManager()
    audit = AuditLogger(log_dir=str(tmp_path / "audit"))
    hub = MCPHub(client=client, planner=planner, security=security, audit=audit)

    project_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["YUNXI_ALLOWED_FILE_ROOTS"] = str(tmp_path)
    env["YUNXI_GUI_MACRO_DIR"] = str(tmp_path / "gui_macros")

    servers = [
        {
            "name": "filesystem",
            "command": sys.executable,
            "args": ["-u", str(project_root / "src" / "core" / "mcp" / "servers" / "filesystem_server.py")],
            "env": env,
            "permissions": {
                "list_dir": [PermissionLevel.READ.value],
                "file_read": [PermissionLevel.READ.value],
                "document_read": [PermissionLevel.READ.value],
                "glob": [PermissionLevel.READ.value],
                "grep": [PermissionLevel.READ.value],
                "file_write": [PermissionLevel.WRITE.value],
                "file_append": [PermissionLevel.WRITE.value],
                "file_copy": [PermissionLevel.WRITE.value],
                "file_move": [PermissionLevel.WRITE.value],
            },
        },
        {
            "name": "browser",
            "command": sys.executable,
            "args": ["-u", str(project_root / "src" / "core" / "mcp" / "servers" / "browser_server.py")],
            "env": env,
            "permissions": {
                "browser_open": [PermissionLevel.NETWORK.value, PermissionLevel.EXECUTE.value],
                "browser_search": [PermissionLevel.NETWORK.value],
                "web_page_read": [PermissionLevel.READ.value, PermissionLevel.NETWORK.value],
                "browser_extract_links": [PermissionLevel.READ.value, PermissionLevel.NETWORK.value],
                "browser_click": [PermissionLevel.NETWORK.value, PermissionLevel.EXECUTE.value],
                "browser_type": [PermissionLevel.WRITE.value, PermissionLevel.EXECUTE.value],
                "browser_session_open": [PermissionLevel.READ.value, PermissionLevel.NETWORK.value],
                "browser_session_snapshot": [PermissionLevel.READ.value],
                "browser_session_click": [PermissionLevel.READ.value, PermissionLevel.NETWORK.value],
                "browser_session_type": [PermissionLevel.WRITE.value],
                "browser_session_fill_form": [PermissionLevel.WRITE.value],
                "browser_session_submit": [PermissionLevel.WRITE.value, PermissionLevel.EXECUTE.value],
            },
        },
        {
            "name": "gui_agent",
            "command": sys.executable,
            "args": ["-u", str(project_root / "src" / "core" / "mcp" / "servers" / "gui_agent_server.py")],
            "env": env,
            "permissions": {
                "gui_observe": [PermissionLevel.READ.value],
                "gui_list_macros": [PermissionLevel.READ.value],
                "gui_macro_stats": [PermissionLevel.READ.value],
                "gui_verify_text": [PermissionLevel.READ.value],
                "gui_save_macro": [PermissionLevel.WRITE.value],
                "gui_run_macro": [PermissionLevel.EXECUTE.value],
                "gui_click": [PermissionLevel.EXECUTE.value],
                "gui_type": [PermissionLevel.WRITE.value, PermissionLevel.EXECUTE.value],
                "gui_hotkey": [PermissionLevel.EXECUTE.value],
                "gui_run_task": [PermissionLevel.EXECUTE.value],
            },
        },
    ]
    await hub.initialize(servers)
    try:
        yield hub, tmp_path
    finally:
        await hub.client.disconnect_all()


async def _ask_and_confirm(
    hub: MCPHub,
    tool_name: str,
    arguments: dict[str, Any],
) -> tuple[str, str, YunxiExecutionEngine]:
    engine = YunxiExecutionEngine(
        llm=OneToolLLM(tool_name, arguments),
        mcp_hub=hub,
        memory_manager=FakeMemory(),
        config=EngineConfig(
            max_turns=1,
            enable_tool_use=True,
            enable_skill_fastpath=False,
        ),
    )
    context = SimpleNamespace(mode="daily_mode")
    first = await engine.respond(f"请使用 {tool_name}", "system", context)
    second = await engine.respond("确认", "system", context)
    return first.content, second.content, engine


def _latest_tool_result(engine: YunxiExecutionEngine) -> str:
    for message in reversed(engine.context.get_messages()):
        if not isinstance(message, UserMessage):
            continue
        if not isinstance(message.content, list):
            continue
        for block in message.content:
            if isinstance(block, ToolResultContentBlock):
                return block.content
    return ""


def _assert_tool_result_ok(engine: YunxiExecutionEngine) -> str:
    content = _latest_tool_result(engine)
    assert content
    assert "工具执行异常" not in content
    assert "[写入失败" not in content
    assert "[执行宏失败" not in content
    assert "[保存宏失败" not in content
    return content


@pytest.mark.asyncio
async def test_yunxi_direct_filesystem_and_document_tools(extended_hub):
    hub, tmp_path = extended_hub
    note = tmp_path / "notes" / "daily.md"

    first, second, engine = await _ask_and_confirm(
        hub,
        "file_write",
        {"path": str(note), "content": "# 云汐\n阶段 6 文件工具验收", "overwrite": True},
    )
    assert "点头" in first
    assert "处理好了" in second
    assert "文件已写入" in _assert_tool_result_ok(engine)

    append_first, append_second, append_engine = await _ask_and_confirm(
        hub,
        "file_append",
        {"path": str(note), "content": "\n追加一行"},
    )
    assert "点头" in append_first
    assert "处理好了" in append_second
    assert "内容已追加" in _assert_tool_result_ok(append_engine)

    read_result = await hub.execute_single("file_read", {"path": str(note)}, SimpleNamespace(mode="daily_mode"))
    list_result = await hub.execute_single("list_dir", {"path": str(tmp_path / "notes")}, SimpleNamespace(mode="daily_mode"))
    glob_result = await hub.execute_single("glob", {"pattern": "**/*.md", "root": str(tmp_path)}, SimpleNamespace(mode="daily_mode"))
    assert "阶段 6 文件工具验收" in read_result.get("content", "")
    assert "追加一行" in read_result.get("content", "")
    assert "daily.md" in list_result.get("content", "")
    assert "daily.md" in glob_result.get("content", "")

    copied = tmp_path / "notes" / "daily-copy.md"
    moved = tmp_path / "notes" / "daily-moved.md"
    _, _, copy_engine = await _ask_and_confirm(
        hub,
        "file_copy",
        {"source_path": str(note), "target_path": str(copied), "overwrite": True},
    )
    assert "文件已复制" in _assert_tool_result_ok(copy_engine)
    _, _, move_engine = await _ask_and_confirm(
        hub,
        "file_move",
        {"source_path": str(copied), "target_path": str(moved), "overwrite": True},
    )
    assert "路径已移动" in _assert_tool_result_ok(move_engine)
    assert moved.exists()

    docx_path = tmp_path / "sample.docx"
    xlsx_path = tmp_path / "sample.xlsx"
    _write_minimal_docx(docx_path, "docx 文档读取验收")
    _write_minimal_xlsx(xlsx_path, "xlsx 表格读取验收")

    docx_result = await hub.execute_single("document_read", {"path": str(docx_path)}, SimpleNamespace(mode="daily_mode"))
    xlsx_result = await hub.execute_single("document_read", {"path": str(xlsx_path)}, SimpleNamespace(mode="daily_mode"))
    grep_result = await hub.execute_single(
        "grep",
        {"pattern": "阶段 6", "root": str(tmp_path), "file_pattern": "*.md"},
        SimpleNamespace(mode="daily_mode"),
    )

    assert "docx 文档读取验收" in docx_result.get("content", "")
    assert "xlsx 表格读取验收" in xlsx_result.get("content", "")
    assert "daily.md" in grep_result.get("content", "")

    secret = tmp_path / ".env"
    secret.write_text("TOKEN=secret", encoding="utf-8")
    secret_read = await hub.execute_single(
        "file_read",
        {"path": str(secret)},
        SimpleNamespace(mode="daily_mode"),
    )
    _, _, secret_write_engine = await _ask_and_confirm(
        hub,
        "file_write",
        {"path": str(secret), "content": "TOKEN=changed", "overwrite": True},
    )
    assert "敏感数据" in secret_read.get("content", "")
    assert "敏感数据" in _latest_tool_result(secret_write_engine)


@pytest.mark.asyncio
async def test_yunxi_direct_browser_tools_with_local_html(extended_hub):
    hub, tmp_path = extended_hub
    page = tmp_path / "index.html"
    page.write_text(
        "<html><body><h1>Yunxi Browser Fixture</h1>"
        "<p>阶段 6 浏览器读取验收。</p>"
        "<a href='next.html'>Next Page</a>"
        "<form action='/submit'><input name='q' placeholder='search'></form>"
        "</body></html>",
        encoding="utf-8",
    )
    (tmp_path / "next.html").write_text("<html><body>next</body></html>", encoding="utf-8")

    read_result = await hub.execute_single(
        "web_page_read",
        {"url": page.as_uri(), "max_chars": 2000},
        SimpleNamespace(mode="daily_mode"),
    )
    links_result = await hub.execute_single(
        "browser_extract_links",
        {"url": page.as_uri(), "max_links": 5},
        SimpleNamespace(mode="daily_mode"),
    )
    search_result = await hub.execute_single(
        "browser_search",
        {"query": "云汐 阶段 6 工具", "engine": "bing", "open_result": False},
        SimpleNamespace(mode="daily_mode"),
    )
    _, _, open_engine = await _ask_and_confirm(
        hub,
        "browser_open",
        {"url": page.as_uri()},
    )
    _, _, click_engine = await _ask_and_confirm(
        hub,
        "browser_click",
        {"url": page.as_uri(), "link_text": "Next Page"},
    )
    _, _, type_engine = await _ask_and_confirm(
        hub,
        "browser_type",
        {"text": "yunxi-browser-type"},
    )
    session_result = await hub.execute_single(
        "browser_session_open",
        {"url": page.as_uri()},
        SimpleNamespace(mode="daily_mode"),
    )
    snapshot_result = await hub.execute_single(
        "browser_session_snapshot",
        {"max_chars": 2000},
        SimpleNamespace(mode="daily_mode"),
    )
    click_session_result = await hub.execute_single(
        "browser_session_click",
        {"link_text": "Next Page"},
        SimpleNamespace(mode="daily_mode"),
    )
    _, _, session_type_engine = await _ask_and_confirm(
        hub,
        "browser_session_fill_form",
        {"fields_json": json.dumps({"q": "yunxi session"})},
    )
    _, _, session_submit_engine = await _ask_and_confirm(
        hub,
        "browser_session_submit",
        {"dry_run": True},
    )

    assert "Yunxi Browser Fixture" in read_result.get("content", "")
    assert "Next Page" in links_result.get("content", "")
    assert "bing.com/search" in search_result.get("content", "")
    assert "浏览器" in _assert_tool_result_ok(open_engine)
    assert "Next Page" in _assert_tool_result_ok(click_engine)
    assert "当前焦点" in _assert_tool_result_ok(type_engine)
    assert "Yunxi Browser Fixture" in session_result.get("content", "")
    assert "表单" in snapshot_result.get("content", "")
    assert "next" in click_session_result.get("content", "")
    assert "yunxi session" in _assert_tool_result_ok(session_type_engine)
    assert "提交预演" in _assert_tool_result_ok(session_submit_engine)


@pytest.mark.asyncio
async def test_yunxi_direct_gui_agent_macro_tools(extended_hub):
    hub, _tmp_path = extended_hub
    steps = json.dumps(
        [
            {"action": "type", "text": "hello {name}"},
            {"action": "hotkey", "keys": "ctrl+s"},
            {"action": "verify_text", "expected_text": "hello {name}"},
        ],
        ensure_ascii=False,
    )

    first, second, engine = await _ask_and_confirm(
        hub,
        "gui_save_macro",
        {
            "name": "daily_macro",
            "steps_json": steps,
            "trigger": "测试宏",
            "window_title_keyword": "Notepad",
        },
    )
    assert "点头" in first
    assert "处理好了" in second
    assert "GUI 宏已保存" in _assert_tool_result_ok(engine)

    list_result = await hub.execute_single("gui_list_macros", {}, SimpleNamespace(mode="daily_mode"))
    assert "daily_macro" in list_result.get("content", "")

    run_first, run_second, run_engine = await _ask_and_confirm(
        hub,
        "gui_run_macro",
        {"name": "daily_macro", "params_json": json.dumps({"name": "yunxi"}), "dry_run": True},
    )
    assert "点头" in run_first
    assert "处理好了" in run_second
    result = _assert_tool_result_ok(run_engine)
    assert "hello yunxi" in result
    assert "verify_text" in result
    assert "Notepad" in result

    stats_result = await hub.execute_single(
        "gui_macro_stats",
        {"name": "daily_macro"},
        SimpleNamespace(mode="daily_mode"),
    )
    assert "window_title_keyword" in stats_result.get("content", "")
    assert "runs" in stats_result.get("content", "")

    failure_steps = json.dumps([{"action": "missing_action"}], ensure_ascii=False)
    _, _, save_failure_macro_engine = await _ask_and_confirm(
        hub,
        "gui_save_macro",
        {"name": "failure_macro", "steps_json": failure_steps},
    )
    assert "GUI 宏已保存" in _assert_tool_result_ok(save_failure_macro_engine)
    _, _, run_failure_macro_engine = await _ask_and_confirm(
        hub,
        "gui_run_macro",
        {"name": "failure_macro", "dry_run": False},
    )
    assert "未知宏动作" in _latest_tool_result(run_failure_macro_engine)
    failure_stats = await hub.execute_single(
        "gui_macro_stats",
        {"name": "failure_macro"},
        SimpleNamespace(mode="daily_mode"),
    )
    assert '"failures": 1' in failure_stats.get("content", "")


@pytest.mark.asyncio
async def test_yunxi_direct_gui_agent_low_risk_actions(extended_hub):
    hub, _tmp_path = extended_hub

    try:
        _, _, run_task_engine = await _ask_and_confirm(
            hub,
            "gui_run_task",
            {"task": "打开 notepad", "dry_run": False},
        )
        assert "Notepad" in _assert_tool_result_ok(run_task_engine)

        await asyncio.sleep(1.0)
        observe_result = await hub.execute_single(
            "gui_observe",
            {"window_title_keyword": "Notepad", "max_controls": 20},
            SimpleNamespace(mode="daily_mode"),
        )
        assert "窗口" in observe_result.get("content", "")

        _, _, type_engine = await _ask_and_confirm(
            hub,
            "gui_type",
            {"text": "yunxi-gui-type"},
        )
        assert "当前焦点" in _assert_tool_result_ok(type_engine)

        _, _, hotkey_engine = await _ask_and_confirm(
            hub,
            "gui_hotkey",
            {"keys": "shift"},
        )
        assert "热键" in _assert_tool_result_ok(hotkey_engine)

        click_result = await hub.execute_single(
            "gui_click",
            {"window_title_keyword": "Notepad", "control_name": "__missing_control__"},
            SimpleNamespace(mode="factory_mode"),
        )
        assert "未找到控件" in click_result.get("content", "")
    finally:
        subprocess.run(
            ["taskkill", "/IM", "notepad.exe", "/F"],
            capture_output=True,
            text=True,
            timeout=10,
        )


def _write_minimal_docx(path: Path, text: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<?xml version='1.0' encoding='UTF-8'?><Types/>")
        archive.writestr(
            "word/document.xml",
            (
                "<?xml version='1.0' encoding='UTF-8'?>"
                "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
                f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
            ),
        )


def _write_minimal_xlsx(path: Path, text: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<?xml version='1.0' encoding='UTF-8'?><Types/>")
        archive.writestr(
            "xl/sharedStrings.xml",
            (
                "<?xml version='1.0' encoding='UTF-8'?>"
                "<sst xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>"
                f"<si><t>{text}</t></si></sst>"
            ),
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            (
                "<?xml version='1.0' encoding='UTF-8'?>"
                "<worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>"
                "<sheetData><row r='1'><c r='A1' t='s'><v>0</v></c></row></sheetData></worksheet>"
            ),
        )
