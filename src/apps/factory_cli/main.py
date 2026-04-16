"""Factory mode terminal entry placeholder.

This module owns the future `yunxi` command.  The full factory engine is still
planned for Phase 6; the current implementation only establishes the command
surface and preserves the current working directory as the target project.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TextIO


IMPLEMENTATION_STATE = "placeholder"


def build_parser() -> argparse.ArgumentParser:
    """Build command-line parser for the factory terminal."""
    parser = argparse.ArgumentParser(
        prog="yunxi",
        description="Start Yunxi factory mode terminal for the current project.",
    )
    parser.add_argument(
        "--project-dir",
        default=None,
        help="Project directory for factory mode. Defaults to the current directory.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print factory entry status and exit.",
    )
    return parser


def resolve_project_dir(value: str | None) -> Path:
    """Resolve the project directory used by the factory session."""
    if value:
        return Path(value).expanduser().resolve()
    return Path.cwd().resolve()


def build_status(project_dir: Path) -> dict[str, str]:
    """Return a machine-readable snapshot for tests and health checks."""
    return {
        "mode": "factory",
        "entry": "yunxi_cli",
        "implementation_state": IMPLEMENTATION_STATE,
        "project_dir": str(project_dir),
        "daily_channel": "feishu",
    }


def run_placeholder_terminal(
    project_dir: Path,
    input_stream: TextIO,
    output_stream: TextIO,
) -> int:
    """Run the temporary interactive shell until the factory engine lands."""
    print("云汐工厂模式入口已就绪。", file=output_stream)
    print(f"当前项目目录：{project_dir}", file=output_stream)
    print("工厂核心引擎将在 Phase 6 接入；现在这是入口占位。", file=output_stream)
    print("输入 /exit 退出。", file=output_stream)

    while True:
        print("远> ", end="", file=output_stream, flush=True)
        line = input_stream.readline()
        if line == "":
            print("", file=output_stream)
            return 0
        command = line.strip()
        if command in {"/exit", "exit", "quit"}:
            print("云汐：工厂模式已退出。日常聊天仍然走飞书。", file=output_stream)
            return 0
        if not command:
            continue
        print(
            "云汐：我先记下这个需求。等工厂引擎接上后，"
            "这里会进入需求澄清、任务拆分和 Worker 调度。",
            file=output_stream,
        )


def main(argv: list[str] | None = None) -> int:
    """Command-line entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)
    project_dir = resolve_project_dir(args.project_dir)

    if args.status:
        print(json.dumps(build_status(project_dir), ensure_ascii=False), flush=True)
        return 0

    return run_placeholder_terminal(project_dir, sys.stdin, sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())

