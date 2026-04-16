"""云汐日常模式 daemon 入口。"""

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from apps.tray.web_server import RuntimeStatus, build_runtime_status
from core.cognition.heart_lake.core import HeartLake
from core.execution.engine import EngineConfig, YunxiExecutionEngine
from core.initiative.continuity import CompanionContinuityService
from core.initiative.event_system import ThreeLayerInitiativeEventSystem
from core.llm.adapter import LLMAdapter
from core.mcp import AuditLogger, DAGPlanner, MCPClient, MCPHub, SecurityManager
from core.mcp.security import PermissionLevel
from core.prompt_builder import PromptConfig, YunxiPromptBuilder
from core.resident.presence import YunxiPresence
from core.runtime import YunxiRuntime
from core.types.message_types import UserMessage
from domains.memory.manager import MemoryManager
from domains.perception.coordinator import PerceptionCoordinator


logger = logging.getLogger(__name__)


@dataclass
class DaemonConfig:
    """Daemon 启动配置。"""

    provider: str = "moonshot"
    memory_path: str = "data/memory"
    continuity_state_path: str = "data/runtime/continuity_state.json"
    initiative_event_library_path: str = "data/initiative/life_events.json"
    initiative_event_state_path: str = "data/runtime/initiative_event_state.json"
    tick_interval: float = 30.0
    enable_tool_use: bool = True
    initialize_desktop_mcp: bool = True
    embedding_provider: Optional[str] = None
    feishu_enabled: bool = False
    deep_llm_ping: bool = True
    run_seconds: Optional[float] = None


@dataclass
class HealthcheckStep:
    """One deep healthcheck step."""

    name: str
    ok: bool
    detail: str = ""


@dataclass
class DeepHealthcheckReport:
    """Deep daemon healthcheck report."""

    status: str
    steps: list[HealthcheckStep] = field(default_factory=list)
    runtime_status: Optional[RuntimeStatus] = None

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        """Append one step and keep details compact."""
        self.steps.append(HealthcheckStep(name=name, ok=ok, detail=detail[:240]))

    def to_dict(self) -> dict[str, object]:
        """Convert to JSON-compatible data."""
        return {
            "status": self.status,
            "steps": [asdict(step) for step in self.steps],
            "runtime_status": self.runtime_status.to_dict()
            if self.runtime_status is not None
            else None,
        }


def load_dotenv(env_path: str = ".env") -> None:
    """加载本地 .env 文件，不覆盖已有环境变量。"""
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


async def build_runtime(config: DaemonConfig) -> YunxiRuntime:
    """构建日常模式 Runtime。"""
    load_dotenv()
    llm = LLMAdapter.from_env(config.provider)
    embedding_provider = config.embedding_provider
    if embedding_provider is None and config.provider.lower() == "ollama":
        embedding_provider = "lexical"
    memory = MemoryManager(
        base_path=config.memory_path,
        embedding_provider=embedding_provider,
    )
    await memory.initialize()

    client = MCPClient()
    planner = DAGPlanner()
    security = SecurityManager()
    audit = AuditLogger(memory_manager=memory)
    mcp_hub = MCPHub(client=client, planner=planner, security=security, audit=audit)
    if config.enable_tool_use:
        await mcp_hub.initialize(
            build_default_tool_server_configs(
                include_desktop=config.initialize_desktop_mcp,
            )
        )

    engine = YunxiExecutionEngine(
        llm=llm,
        mcp_hub=mcp_hub,
        memory_manager=memory,
        config=EngineConfig(enable_tool_use=config.enable_tool_use),
    )

    return YunxiRuntime(
        engine=engine,
        prompt_builder=YunxiPromptBuilder(PromptConfig()),
        heart_lake=HeartLake(),
        perception=PerceptionCoordinator(),
        memory=memory,
        continuity=CompanionContinuityService(
            storage_path=Path(config.continuity_state_path),
        ),
        initiative_event_system=ThreeLayerInitiativeEventSystem(
            library_path=Path(config.initiative_event_library_path),
            state_path=Path(config.initiative_event_state_path),
        ),
        mcp_hub=mcp_hub,
    )


def build_desktop_server_config() -> dict[str, object]:
    """构建日常模式默认 Desktop MCP Server 配置。"""
    project_root = Path(__file__).resolve().parents[3]
    server_path = project_root / "src" / "core" / "mcp" / "servers" / "desktop_server.py"
    env = os.environ.copy()
    src_path = str(project_root / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    return {
        "name": "desktop",
        "command": sys.executable,
        "args": ["-u", str(server_path)],
        "env": env,
        "permissions": {
            "screenshot_capture": [PermissionLevel.WRITE.value],
            "clipboard_read": [PermissionLevel.READ.value],
            "clipboard_write": [PermissionLevel.WRITE.value],
            "desktop_notify": [PermissionLevel.WRITE.value],
            "app_launch_ui": [PermissionLevel.EXECUTE.value],
            "window_focus_ui": [PermissionLevel.EXECUTE.value],
            "window_minimize_ui": [PermissionLevel.EXECUTE.value],
        },
    }


def build_default_tool_server_configs(include_desktop: bool = True) -> list[dict[str, object]]:
    """构建日常模式默认 MCP Server 配置。"""
    configs = [
        build_filesystem_server_config(),
        build_browser_server_config(),
        build_gui_agent_server_config(),
    ]
    if include_desktop:
        configs.insert(0, build_desktop_server_config())
    return configs


def _build_server_env(extra: Optional[dict[str, str]] = None) -> dict[str, str]:
    project_root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    src_path = str(project_root / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    if "YUNXI_ALLOWED_FILE_ROOTS" not in env:
        roots = [str(project_root), str(Path.home())]
        d_drive = Path("D:/")
        if d_drive.exists():
            roots.append(str(d_drive))
        env["YUNXI_ALLOWED_FILE_ROOTS"] = os.pathsep.join(roots)
    if extra:
        env.update(extra)
    return env


def build_filesystem_server_config() -> dict[str, object]:
    """构建 Filesystem/Document MCP Server 配置。"""
    project_root = Path(__file__).resolve().parents[3]
    server_path = project_root / "src" / "core" / "mcp" / "servers" / "filesystem_server.py"
    return {
        "name": "filesystem",
        "command": sys.executable,
        "args": ["-u", str(server_path)],
        "env": _build_server_env(),
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
    }


def build_browser_server_config() -> dict[str, object]:
    """构建 Browser MCP Server 配置。"""
    project_root = Path(__file__).resolve().parents[3]
    server_path = project_root / "src" / "core" / "mcp" / "servers" / "browser_server.py"
    return {
        "name": "browser",
        "command": sys.executable,
        "args": ["-u", str(server_path)],
        "env": _build_server_env(),
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
    }


def build_gui_agent_server_config() -> dict[str, object]:
    """构建 GUI Agent MCP Server 配置。"""
    project_root = Path(__file__).resolve().parents[3]
    server_path = project_root / "src" / "core" / "mcp" / "servers" / "gui_agent_server.py"
    return {
        "name": "gui_agent",
        "command": sys.executable,
        "args": ["-u", str(server_path)],
        "env": _build_server_env(),
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
    }


async def run_healthcheck(config: DaemonConfig) -> RuntimeStatus:
    """构建 Runtime 并返回状态快照，用于启动前健康检查。"""
    runtime = await build_runtime(config)
    try:
        return build_runtime_status(runtime)
    finally:
        await close_runtime(runtime)


async def run_deep_healthcheck(config: DaemonConfig) -> DeepHealthcheckReport:
    """Run a deeper daily-mode readiness check."""
    report = DeepHealthcheckReport(status="failed")
    runtime: Optional[YunxiRuntime] = None

    try:
        runtime = await build_runtime(config)
        report.add("runtime_build", True, "runtime constructed")
    except Exception as exc:
        report.add("runtime_build", False, str(exc))
        return report

    try:
        report.runtime_status = build_runtime_status(runtime)
        report.add("runtime_status", True, "status snapshot built")
    except Exception as exc:
        report.add("runtime_status", False, str(exc))

    if config.deep_llm_ping:
        try:
            response = await runtime.engine.llm.complete(
                system="你是云汐。请只回复：在。",
                messages=[UserMessage(content="健康检查")],
                tools=None,
            )
            ok = bool(getattr(response, "content", "").strip())
            report.add("llm_ping", ok, "llm returned content" if ok else "empty response")
        except Exception as exc:
            report.add("llm_ping", False, str(exc))
    else:
        report.add("llm_ping", True, "skipped by configuration")

    try:
        runtime.memory.get_memory_summary(limit=1)
        report.add("memory", True, "memory summary available")
    except Exception as exc:
        report.add("memory", False, str(exc))

    report.add(
        "event_library",
        *_check_event_library(Path(config.initiative_event_library_path)),
    )
    report.add(
        "continuity_rw",
        *_check_continuity_read_write(Path(config.continuity_state_path)),
    )
    report.add("feishu_config", *_check_feishu_config(config.feishu_enabled))

    try:
        await close_runtime(runtime)
        runtime = None
        report.add("resource_close", True, "runtime resources closed")
    except Exception as exc:
        report.add("resource_close", False, str(exc))
    finally:
        if runtime is not None:
            try:
                await close_runtime(runtime)
            except Exception:
                logger.exception("Failed to close runtime after deep healthcheck")

    report.status = "passed" if all(step.ok for step in report.steps) else "failed"
    return report


def _check_event_library(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing: {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, str(exc)
    if not isinstance(data, list) or not data:
        return False, "event library must be a non-empty list"
    return True, f"{len(data)} events"


def _check_continuity_read_write(path: Path) -> tuple[bool, str]:
    probe_path = path.with_suffix(path.suffix + ".healthcheck.json")
    try:
        probe = CompanionContinuityService(storage_path=probe_path)
        probe.record_exchange("healthcheck", "ok")
        reloaded = CompanionContinuityService(storage_path=probe_path)
        ok = bool(reloaded.exchanges and reloaded.exchanges[-1].assistant_message == "ok")
        return (ok, "read/write ok" if ok else "probe exchange missing")
    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            probe_path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Failed to remove continuity healthcheck probe: %s", exc)


def _check_feishu_config(enabled: bool) -> tuple[bool, str]:
    if not enabled:
        return True, "disabled"
    app_id = os.getenv("FEISHU_APP_ID", "")
    app_secret = os.getenv("FEISHU_APP_SECRET", "")
    receiver_id = os.getenv("FEISHU_RECEIVER_ID", "")
    missing = [
        name
        for name, value in (
            ("FEISHU_APP_ID", app_id),
            ("FEISHU_APP_SECRET", app_secret),
            ("FEISHU_RECEIVER_ID", receiver_id),
        )
        if not value
    ]
    if missing:
        return False, "missing " + ", ".join(missing)
    return True, "configured"


async def run_daemon(config: DaemonConfig) -> None:
    """启动日常模式 daemon。"""
    runtime = await build_runtime(config)

    feishu_ws: Optional[Any] = None

    if config.feishu_enabled:
        # 使用飞书作为消息通道
        from interfaces.feishu.adapter import FeishuAdapter
        from interfaces.feishu.client import get_feishu_client
        from interfaces.feishu.websocket import FeishuWebSocket

        feishu_client = get_feishu_client()
        if not feishu_client.is_configured:
            print("[警告] 飞书未配置或配置不完整，将使用 print 模式", flush=True)
            config.feishu_enabled = False
        else:
            adapter = FeishuAdapter(
                runtime=runtime,
                feishu_client=feishu_client,
                event_loop=asyncio.get_running_loop(),
            )
            proactive_cb = adapter.create_proactive_callback()

            async def on_proactive_message(message: str) -> None:
                await proactive_cb(message)

            def on_feishu_message(user_id: str, chat_id: str, content: str) -> None:
                print(f"[飞书] 收到消息 from {user_id}: {content[:50]}", flush=True)
                adapter.on_feishu_message(user_id, chat_id, content)

            feishu_ws = FeishuWebSocket(on_message=on_feishu_message)
            feishu_ws.start()
            print("[飞书] WebSocket 已启动，等待消息...", flush=True)

            presence = YunxiPresence(
                proactive_tick=runtime.proactive_tick,
                on_proactive_message=on_proactive_message,
                tick_interval=config.tick_interval,
                memory_manager=runtime.memory,
            )
            presence.start()
            print("[云汐] 日常模式已启动，可以通过飞书和我聊天了～", flush=True)
            try:
                await _wait_for_shutdown_window(config.run_seconds)
            finally:
                await presence.stop()
                feishu_ws.stop()
                await close_runtime(runtime)
            return

    # 非飞书模式：使用 print
    async def on_proactive_message(message: str) -> None:
        print(message, flush=True)

    presence = YunxiPresence(
        proactive_tick=runtime.proactive_tick,
        on_proactive_message=on_proactive_message,
        tick_interval=config.tick_interval,
        memory_manager=runtime.memory,
    )
    presence.start()
    try:
        await _wait_for_shutdown_window(config.run_seconds)
    finally:
        await presence.stop()
        await close_runtime(runtime)


async def _wait_for_shutdown_window(run_seconds: Optional[float]) -> None:
    """Wait forever or for a bounded live-test window."""
    if run_seconds is None:
        while True:
            await asyncio.sleep(3600)
    else:
        await asyncio.sleep(max(0.0, run_seconds))


async def close_runtime(runtime: YunxiRuntime) -> None:
    """释放 Runtime 持有的外部资源。"""
    if runtime.mcp_hub is not None:
        await runtime.mcp_hub.client.disconnect_all()
    llm = getattr(runtime.engine, "llm", None)
    provider = getattr(llm, "provider", None)
    if provider is not None:
        await provider.close()
    close_perception = getattr(runtime.perception, "close", None)
    if callable(close_perception):
        close_perception()
    await runtime.memory.close()


def parse_args() -> argparse.Namespace:
    """解析 daemon 命令行参数。"""
    parser = argparse.ArgumentParser(description="云汐日常模式 daemon")
    parser.add_argument("--provider", default="moonshot")
    parser.add_argument("--memory-path", default="data/memory")
    parser.add_argument("--continuity-state-path", default="data/runtime/continuity_state.json")
    parser.add_argument("--initiative-event-library-path", default="data/initiative/life_events.json")
    parser.add_argument("--initiative-event-state-path", default="data/runtime/initiative_event_state.json")
    parser.add_argument("--tick-interval", type=float, default=30.0)
    parser.add_argument("--healthcheck", action="store_true")
    parser.add_argument("--healthcheck-deep", action="store_true")
    parser.add_argument("--skip-llm-ping", action="store_true")
    parser.add_argument("--disable-tool-use", action="store_true")
    parser.add_argument("--skip-desktop-mcp", action="store_true")
    parser.add_argument("--feishu-enable", action="store_true", help="启用飞书消息通道")
    parser.add_argument(
        "--run-seconds",
        type=float,
        default=None,
        help="有界运行秒数；用于 live 验收时自动退出",
    )
    parser.add_argument(
        "--embedding-provider",
        choices=["sentence_transformers", "lexical", "ollama"],
        default=None,
    )
    return parser.parse_args()


async def async_main() -> None:
    """Daemon 异步入口。"""
    args = parse_args()
    config = DaemonConfig(
        provider=args.provider,
        memory_path=args.memory_path,
        continuity_state_path=args.continuity_state_path,
        initiative_event_library_path=args.initiative_event_library_path,
        initiative_event_state_path=args.initiative_event_state_path,
        tick_interval=args.tick_interval,
        enable_tool_use=not args.disable_tool_use,
        initialize_desktop_mcp=not args.skip_desktop_mcp,
        embedding_provider=args.embedding_provider,
        feishu_enabled=args.feishu_enable,
        deep_llm_ping=not args.skip_llm_ping,
        run_seconds=args.run_seconds,
    )
    if args.healthcheck_deep:
        report = await run_deep_healthcheck(config)
        print(json.dumps(report.to_dict(), ensure_ascii=False), flush=True)
        if report.status != "passed":
            raise SystemExit(1)
        return
    if args.healthcheck:
        status = await run_healthcheck(config)
        print(status.to_dict(), flush=True)
        return
    await run_daemon(config)


def main() -> None:
    """Daemon 命令行入口。"""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
