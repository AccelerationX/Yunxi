"""Tray/WebUI 状态控制面板数据适配。

正式日常对话统一走飞书；这里只暴露状态、日志和本地控制面板所需数据。
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from core.runtime import YunxiRuntime


@dataclass
class RuntimeStatus:
    """Runtime 暴露给 Tray/WebUI 状态控制面板的状态快照。"""

    mode: str
    emotion: str
    miss_value: float
    focused_application: str
    foreground_process_name: str = ""
    activity_state: str = ""
    is_fullscreen: bool = False
    input_events_per_minute: float = 0.0
    available_tools: List[str] = field(default_factory=list)
    continuity_size: int = 0
    unanswered_proactive_count: int = 0
    recent_proactive_count: int = 0
    presence_murmur_count: int = 0
    presence_murmur_count_date: str = ""
    last_presence_murmur_at: float = 0.0
    recent_presence_murmurs: List[str] = field(default_factory=list)
    pending_confirmation_count: int = 0
    recent_tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    skill_candidate_count: int = 0
    skill_candidates: List[Dict[str, Any]] = field(default_factory=list)
    daily_channel: str = "feishu"
    factory_entry_command: str = "yunxi"

    def to_dict(self) -> Dict[str, object]:
        """转换为 Web JSON 可序列化结构。"""
        return asdict(self)


@dataclass
class ControlPanelSnapshot:
    """Data shown by the simplified WebUI/Tray control panel."""

    runtime_status: RuntimeStatus
    recent_logs: List[str] = field(default_factory=list)
    factory_entry_command: str = "yunxi"

    def to_dict(self) -> Dict[str, object]:
        """转换为 Web JSON 可序列化结构。"""
        return asdict(self)


def build_runtime_status(runtime: YunxiRuntime) -> RuntimeStatus:
    """从 Runtime 构建 Tray/WebUI 状态控制面板快照。"""
    context = runtime.get_context()
    heart_lake = context.heart_lake_state
    perception = context.perception_snapshot
    focused_application = ""
    foreground_process_name = ""
    activity_state = ""
    is_fullscreen = False
    input_events_per_minute = 0.0
    if perception and perception.user_presence:
        presence = perception.user_presence
        focused_application = presence.focused_application
        foreground_process_name = getattr(presence, "foreground_process_name", "")
        activity_state = getattr(presence, "activity_state", "")
        is_fullscreen = bool(getattr(presence, "is_fullscreen", False))
        input_events_per_minute = float(
            getattr(presence, "input_events_per_minute", 0.0) or 0.0
        )

    return RuntimeStatus(
        mode=context.mode,
        emotion=getattr(heart_lake, "current_emotion", "平静"),
        miss_value=float(getattr(heart_lake, "miss_value", 0.0)),
        focused_application=focused_application,
        foreground_process_name=foreground_process_name,
        activity_state=activity_state,
        is_fullscreen=is_fullscreen,
        input_events_per_minute=input_events_per_minute,
        available_tools=list(context.available_tools),
        continuity_size=len(runtime.continuity.exchanges),
        unanswered_proactive_count=runtime.continuity.unanswered_proactive_count,
        recent_proactive_count=getattr(runtime.continuity, "recent_proactive_count", 0),
        presence_murmur_count=getattr(runtime.continuity, "presence_murmur_count", 0),
        presence_murmur_count_date=getattr(
            runtime.continuity, "presence_murmur_count_date", ""
        ),
        last_presence_murmur_at=getattr(runtime.continuity, "last_presence_murmur_at", 0.0),
        recent_presence_murmurs=list(
            getattr(runtime.continuity, "recent_presence_murmurs", [])[-6:]
        ),
        pending_confirmation_count=_pending_confirmation_count(runtime),
        recent_tool_calls=_recent_tool_calls(runtime),
        skill_candidate_count=len(_skill_candidates(runtime)),
        skill_candidates=_skill_candidates(runtime),
    )


def build_control_panel_snapshot(
    runtime: YunxiRuntime,
    log_paths: List[str | Path] | None = None,
    max_log_lines: int = 80,
) -> ControlPanelSnapshot:
    """Build the simplified WebUI/Tray control panel snapshot."""
    return ControlPanelSnapshot(
        runtime_status=build_runtime_status(runtime),
        recent_logs=read_recent_log_lines(log_paths or [], max_lines=max_log_lines),
    )


def read_recent_log_lines(
    log_paths: List[str | Path],
    max_lines: int = 80,
) -> List[str]:
    """Read recent log lines from the first existing log files."""
    lines: List[str] = []
    for raw_path in log_paths:
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            continue
        try:
            file_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        lines.extend(file_lines[-max_lines:])
    return lines[-max_lines:]


def create_status_app(
    runtime: YunxiRuntime,
    log_paths: List[str | Path] | None = None,
):
    """Create a lightweight aiohttp app for status, logs, and factory entry."""
    from aiohttp import web

    async def index(request):
        return web.Response(text=_render_index_html(), content_type="text/html")

    async def status(request):
        return web.json_response(build_runtime_status(runtime).to_dict())

    async def logs(request):
        return web.json_response(
            {"lines": read_recent_log_lines(log_paths or [])}
        )

    async def factory_entry(request):
        return web.json_response(
            {
                "command": "yunxi",
                "description": "在目标项目目录打开终端并执行 yunxi",
            }
        )

    async def skill_candidates(request):
        return web.json_response({"candidates": _skill_candidates(runtime, limit=50)})

    async def approve_skill(request):
        data = await request.json()
        skill_name = str(data.get("skill_name", ""))
        ok = _approve_skill_candidate(runtime, skill_name)
        return web.json_response({"ok": ok, "skill_name": skill_name})

    async def reject_skill(request):
        data = await request.json()
        skill_name = str(data.get("skill_name", ""))
        ok = _reject_skill_candidate(runtime, skill_name)
        return web.json_response({"ok": ok, "skill_name": skill_name})

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/api/status", status)
    app.router.add_get("/api/logs", logs)
    app.router.add_get("/api/factory-entry", factory_entry)
    app.router.add_get("/api/skills/candidates", skill_candidates)
    app.router.add_post("/api/skills/approve", approve_skill)
    app.router.add_post("/api/skills/reject", reject_skill)
    return app


def _render_index_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>云汐状态</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 24px; line-height: 1.5; }
    button { border-radius: 6px; padding: 8px 12px; }
    pre { white-space: pre-wrap; border: 1px solid #ddd; padding: 12px; }
  </style>
</head>
<body>
  <h1>云汐状态</h1>
  <button onclick="loadStatus()">刷新状态</button>
  <button onclick="loadLogs()">查看日志</button>
  <button onclick="loadFactory()">工厂模式入口</button>
  <pre id="output">等待刷新。</pre>
  <script>
    async function show(url) {
      const res = await fetch(url);
      document.getElementById('output').textContent =
        JSON.stringify(await res.json(), null, 2);
    }
    function loadStatus() { show('/api/status'); }
    function loadLogs() { show('/api/logs'); }
    function loadFactory() { show('/api/factory-entry'); }
    loadStatus();
  </script>
</body>
</html>"""


def _pending_confirmation_count(runtime: YunxiRuntime) -> int:
    hub = getattr(runtime, "mcp_hub", None)
    if hub is None:
        return 0
    pending = getattr(hub, "list_pending_confirmations", None)
    if not callable(pending):
        return 0
    return len(pending())


def _recent_tool_calls(runtime: YunxiRuntime, limit: int = 6) -> List[Dict[str, Any]]:
    hub = getattr(runtime, "mcp_hub", None)
    audit = getattr(hub, "audit", None) if hub is not None else None
    entries_fn = getattr(audit, "get_today_entries", None)
    if not callable(entries_fn):
        return []
    try:
        entries = entries_fn()
    except Exception:
        return []
    rows: List[Dict[str, Any]] = []
    for entry in entries[-limit:]:
        plan = entry.get("plan", []) if isinstance(entry, dict) else []
        results = entry.get("results", []) if isinstance(entry, dict) else []
        rows.append(
            {
                "timestamp": entry.get("timestamp", ""),
                "tools": [item.get("tool", "") for item in plan if isinstance(item, dict)],
                "ok": all(not item.get("is_error", False) for item in results if isinstance(item, dict)),
            }
        )
    return rows


def _skill_candidates(runtime: YunxiRuntime, limit: int = 6) -> List[Dict[str, Any]]:
    memory = getattr(runtime, "memory", None)
    list_fn = getattr(memory, "list_skill_candidates", None)
    if not callable(list_fn):
        return []
    try:
        candidates = list_fn()
    except Exception:
        return []
    rows: List[Dict[str, Any]] = []
    for item in candidates[:limit]:
        rows.append(
            {
                "skill_name": item.get("skill_name", ""),
                "trigger_patterns": item.get("trigger_patterns", []),
                "actions": item.get("actions", []),
                "candidate_reason": item.get("candidate_reason", ""),
                "status": item.get("status", ""),
            }
        )
    return rows


def _approve_skill_candidate(runtime: YunxiRuntime, skill_name: str) -> bool:
    memory = getattr(runtime, "memory", None)
    approve = getattr(memory, "approve_skill_candidate", None)
    if not callable(approve) or not skill_name:
        return False
    return bool(approve(skill_name))


def _reject_skill_candidate(runtime: YunxiRuntime, skill_name: str) -> bool:
    memory = getattr(runtime, "memory", None)
    reject = getattr(memory, "reject_skill_candidate", None)
    if not callable(reject) or not skill_name:
        return False
    return bool(reject(skill_name))
