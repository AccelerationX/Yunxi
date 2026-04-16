"""Filesystem and document MCP Server."""

from __future__ import annotations

import csv
import fnmatch
import json
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Iterable, Optional
from xml.etree import ElementTree

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("yunxi-filesystem")


def _default_roots() -> list[Path]:
    roots = [Path.cwd()]
    home = Path.home()
    if home not in roots:
        roots.append(home)
    drive = Path("D:/")
    if drive.exists() and drive not in roots:
        roots.append(drive)
    return roots


def _allowed_roots() -> list[Path]:
    raw = os.getenv("YUNXI_ALLOWED_FILE_ROOTS", "")
    items = [item for item in raw.split(os.pathsep) if item.strip()]
    roots = [Path(item).expanduser().resolve() for item in items] if items else _default_roots()
    return roots


def _resolve_user_path(path: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    resolved = candidate.resolve()
    for root in _allowed_roots():
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    roots_text = "; ".join(str(root) for root in _allowed_roots())
    raise PermissionError(f"路径不在允许根目录内：{resolved}；允许根目录：{roots_text}")


def _is_sensitive_path(path: Path) -> bool:
    lowered_parts = [part.lower() for part in path.parts]
    name = path.name.lower()
    sensitive_names = {
        ".env",
        ".env.local",
        ".env.production",
        "id_rsa",
        "id_ed25519",
        "credentials.json",
        "token.json",
        "cookies.sqlite",
        "login data",
        "history",
    }
    sensitive_suffixes = {".pem", ".key", ".p12", ".pfx", ".sqlite", ".db"}
    sensitive_dirs = {
        ".ssh",
        ".gnupg",
        "cookies",
        "local storage",
        "session storage",
        "user data",
        "browser",
    }
    return (
        name in sensitive_names
        or path.suffix.lower() in sensitive_suffixes
        or any(part in sensitive_dirs for part in lowered_parts)
    )


def _sensitive_path_guard(path: Path, operation: str) -> Optional[str]:
    if os.getenv("YUNXI_ALLOW_SENSITIVE_FILES") == "1":
        return None
    if not _is_sensitive_path(path):
        return None
    return (
        f"[{operation}已拦截：{path} 看起来包含密钥、令牌、Cookie、浏览器配置"
        "或数据库等敏感数据。若远明确需要处理，请先人工确认并设置 "
        "YUNXI_ALLOW_SENSITIVE_FILES=1。]"
    )


def _read_text(path: Path, max_chars: int) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[: max(200, max_chars)]


@mcp.tool()
def list_dir(path: str = ".", max_entries: int = 200) -> str:
    """List files and folders under a directory."""
    try:
        root = _resolve_user_path(path)
        if not root.is_dir():
            return f"[列目录失败：不是目录：{root}]"
        rows = []
        for item in sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:max_entries]:
            kind = "dir" if item.is_dir() else "file"
            size = "" if item.is_dir() else str(item.stat().st_size)
            rows.append(f"{kind}\t{size}\t{item.name}")
        return "\n".join(rows) if rows else "[目录为空]"
    except Exception as exc:
        return f"[列目录失败：{exc}]"


@mcp.tool()
def file_read(path: str, max_chars: int = 8000) -> str:
    """Read a UTF-8 text file."""
    try:
        resolved = _resolve_user_path(path)
        if not resolved.is_file():
            return f"[读取失败：不是文件：{resolved}]"
        blocked = _sensitive_path_guard(resolved, "读取")
        if blocked:
            return blocked
        return _read_text(resolved, max_chars)
    except Exception as exc:
        return f"[读取失败：{exc}]"


@mcp.tool()
def file_write(path: str, content: str, overwrite: bool = False) -> str:
    """Write a UTF-8 text file. Existing files require overwrite=true."""
    try:
        resolved = _resolve_user_path(path)
        blocked = _sensitive_path_guard(resolved, "写入")
        if blocked:
            return blocked
        if resolved.exists() and not overwrite:
            return f"[写入失败：文件已存在，如需覆盖请设置 overwrite=true：{resolved}]"
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"文件已写入：{resolved}"
    except Exception as exc:
        return f"[写入失败：{exc}]"


@mcp.tool()
def file_append(path: str, content: str) -> str:
    """Append UTF-8 text to a file."""
    try:
        resolved = _resolve_user_path(path)
        blocked = _sensitive_path_guard(resolved, "追加")
        if blocked:
            return blocked
        resolved.parent.mkdir(parents=True, exist_ok=True)
        with resolved.open("a", encoding="utf-8") as file:
            file.write(content)
        return f"内容已追加：{resolved}"
    except Exception as exc:
        return f"[追加失败：{exc}]"


@mcp.tool()
def file_copy(source_path: str, target_path: str, overwrite: bool = False) -> str:
    """Copy a file."""
    try:
        source = _resolve_user_path(source_path)
        target = _resolve_user_path(target_path)
        blocked = _sensitive_path_guard(source, "复制") or _sensitive_path_guard(target, "复制")
        if blocked:
            return blocked
        if not source.is_file():
            return f"[复制失败：源文件不存在：{source}]"
        if target.exists() and not overwrite:
            return f"[复制失败：目标已存在，如需覆盖请设置 overwrite=true：{target}]"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return f"文件已复制：{source} -> {target}"
    except Exception as exc:
        return f"[复制失败：{exc}]"


@mcp.tool()
def file_move(source_path: str, target_path: str, overwrite: bool = False) -> str:
    """Move or rename a file."""
    try:
        source = _resolve_user_path(source_path)
        target = _resolve_user_path(target_path)
        blocked = _sensitive_path_guard(source, "移动") or _sensitive_path_guard(target, "移动")
        if blocked:
            return blocked
        if not source.exists():
            return f"[移动失败：源路径不存在：{source}]"
        if target.exists() and not overwrite:
            return f"[移动失败：目标已存在，如需覆盖请设置 overwrite=true：{target}]"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        return f"路径已移动：{source} -> {target}"
    except Exception as exc:
        return f"[移动失败：{exc}]"


@mcp.tool()
def glob(pattern: str, root: str = ".", max_matches: int = 200) -> str:
    """Find paths by glob pattern under an allowed root."""
    try:
        base = _resolve_user_path(root)
        matches = sorted(base.glob(pattern))[:max_matches]
        return "\n".join(str(path) for path in matches) if matches else "[没有匹配路径]"
    except Exception as exc:
        return f"[glob 失败：{exc}]"


@mcp.tool()
def grep(pattern: str, root: str = ".", file_pattern: str = "*", max_matches: int = 80) -> str:
    """Search text files by regex pattern under a root."""
    try:
        base = _resolve_user_path(root)
        regex = re.compile(pattern)
        rows: list[str] = []
        for path in _iter_files(base, file_pattern):
            try:
                for idx, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if regex.search(line):
                        rows.append(f"{path}:{idx}: {line[:240]}")
                        if len(rows) >= max_matches:
                            return "\n".join(rows)
            except OSError:
                continue
        return "\n".join(rows) if rows else "[没有匹配文本]"
    except Exception as exc:
        return f"[grep 失败：{exc}]"


def _iter_files(root: Path, file_pattern: str) -> Iterable[Path]:
    if root.is_file():
        yield root
        return
    for path in root.rglob("*"):
        if path.is_file() and fnmatch.fnmatch(path.name, file_pattern):
            yield path


@mcp.tool()
def document_read(path: str, max_chars: int = 12000) -> str:
    """Read common document formats: text/markdown/json/csv/docx/xlsx/pdf."""
    try:
        resolved = _resolve_user_path(path)
        if not resolved.is_file():
            return f"[文档读取失败：不是文件：{resolved}]"
        blocked = _sensitive_path_guard(resolved, "文档读取")
        if blocked:
            return blocked
        suffix = resolved.suffix.lower()
        if suffix in {".txt", ".md", ".markdown", ".json", ".csv", ".py", ".yaml", ".yml", ".log"}:
            return _read_text(resolved, max_chars)
        if suffix == ".docx":
            return _read_docx(resolved)[: max(200, max_chars)]
        if suffix == ".xlsx":
            return _read_xlsx(resolved)[: max(200, max_chars)]
        if suffix == ".pdf":
            return _read_pdf(resolved)[: max(200, max_chars)]
        return f"[文档读取失败：暂不支持格式 {suffix}]"
    except Exception as exc:
        return f"[文档读取失败：{exc}]"


def _read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    texts = [node.text or "" for node in root.iter() if node.tag.endswith("}t")]
    return " ".join("".join(texts).split())


def _read_xlsx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        shared = _read_xlsx_shared_strings(archive)
        sheet_names = [name for name in archive.namelist() if name.startswith("xl/worksheets/sheet")]
        rows: list[str] = []
        for sheet_name in sheet_names[:5]:
            root = ElementTree.fromstring(archive.read(sheet_name))
            rows.append(f"[{sheet_name}]")
            for row in root.iter():
                if not row.tag.endswith("}row"):
                    continue
                values = []
                for cell in row:
                    if not cell.tag.endswith("}c"):
                        continue
                    cell_type = cell.attrib.get("t")
                    value = ""
                    for child in cell:
                        if child.tag.endswith("}v") and child.text is not None:
                            value = child.text
                    if cell_type == "s" and value.isdigit():
                        value = shared[int(value)] if int(value) < len(shared) else value
                    values.append(value)
                if values:
                    rows.append(",".join(values))
        return "\n".join(rows)


def _read_xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for si in root:
        texts = [node.text or "" for node in si.iter() if node.tag.endswith("}t")]
        values.append("".join(texts))
    return values


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        try:
            from PyPDF2 import PdfReader
        except Exception:
            return "[PDF 读取降级：当前环境未安装 pypdf/PyPDF2]"
    reader = PdfReader(str(path))
    texts = []
    for page in reader.pages[:20]:
        texts.append(page.extract_text() or "")
    return "\n".join(texts)


if __name__ == "__main__":
    mcp.run(transport="stdio")
