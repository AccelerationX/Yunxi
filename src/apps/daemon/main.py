"""云汐日常模式 daemon 入口。"""

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from apps.tray.web_server import RuntimeStatus, build_runtime_status
from core.cognition.heart_lake.core import HeartLake
from core.execution.engine import EngineConfig, YunxiExecutionEngine
from core.initiative.continuity import CompanionContinuityService
from core.llm.adapter import LLMAdapter
from core.mcp import AuditLogger, DAGPlanner, MCPClient, MCPHub, SecurityManager
from core.mcp.security import PermissionLevel
from core.prompt_builder import PromptConfig, YunxiPromptBuilder
from core.resident.presence import YunxiPresence
from core.runtime import YunxiRuntime
from domains.memory.manager import MemoryManager
from domains.perception.coordinator import PerceptionCoordinator


@dataclass
class DaemonConfig:
    """Daemon 启动配置。"""

    provider: str = "moonshot"
    memory_path: str = "data/memory"
    tick_interval: float = 30.0
    enable_tool_use: bool = True
    initialize_desktop_mcp: bool = True
    embedding_provider: Optional[str] = None


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
    if config.enable_tool_use and config.initialize_desktop_mcp:
        await mcp_hub.initialize([build_desktop_server_config()])

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
        continuity=CompanionContinuityService(),
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


async def run_healthcheck(config: DaemonConfig) -> RuntimeStatus:
    """构建 Runtime 并返回状态快照，用于启动前健康检查。"""
    runtime = await build_runtime(config)
    try:
        return build_runtime_status(runtime)
    finally:
        await close_runtime(runtime)


async def run_daemon(config: DaemonConfig) -> None:
    """启动日常模式 daemon。"""
    runtime = await build_runtime(config)

    async def on_proactive_message(message: str) -> None:
        print(message, flush=True)

    presence = YunxiPresence(
        proactive_tick=runtime.proactive_tick,
        on_proactive_message=on_proactive_message,
        tick_interval=config.tick_interval,
    )
    presence.start()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await presence.stop()
        await close_runtime(runtime)


async def close_runtime(runtime: YunxiRuntime) -> None:
    """释放 Runtime 持有的外部资源。"""
    if runtime.mcp_hub is not None:
        await runtime.mcp_hub.client.disconnect_all()
    llm = getattr(runtime.engine, "llm", None)
    provider = getattr(llm, "provider", None)
    if provider is not None:
        await provider.close()


def parse_args() -> argparse.Namespace:
    """解析 daemon 命令行参数。"""
    parser = argparse.ArgumentParser(description="云汐日常模式 daemon")
    parser.add_argument("--provider", default="moonshot")
    parser.add_argument("--memory-path", default="data/memory")
    parser.add_argument("--tick-interval", type=float, default=30.0)
    parser.add_argument("--healthcheck", action="store_true")
    parser.add_argument("--disable-tool-use", action="store_true")
    parser.add_argument("--skip-desktop-mcp", action="store_true")
    parser.add_argument(
        "--embedding-provider",
        choices=["sentence_transformers", "lexical"],
        default=None,
    )
    return parser.parse_args()


async def async_main() -> None:
    """Daemon 异步入口。"""
    args = parse_args()
    config = DaemonConfig(
        provider=args.provider,
        memory_path=args.memory_path,
        tick_interval=args.tick_interval,
        enable_tool_use=not args.disable_tool_use,
        initialize_desktop_mcp=not args.skip_desktop_mcp,
        embedding_provider=args.embedding_provider,
    )
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
