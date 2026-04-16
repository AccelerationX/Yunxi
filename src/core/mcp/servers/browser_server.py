"""Browser MCP Server.

Provides lightweight browser and web-page tools without requiring Playwright.
The stable path is URL construction, local/HTTP HTML reading, and link
extraction. Full browser automation can be layered behind the same tool names
later.
"""

from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
import webbrowser
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("yunxi-browser")


class _ReadableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_stack: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._current_link: Optional[str] = None
        self._current_link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_stack.append(tag)
            return
        if tag == "a":
            attrs_dict = dict(attrs)
            self._current_link = attrs_dict.get("href")
            self._current_link_text = []
        if tag in {"p", "div", "section", "article", "br", "li", "tr", "h1", "h2", "h3"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._skip_stack and self._skip_stack[-1] == tag:
            self._skip_stack.pop()
            return
        if tag == "a" and self._current_link:
            label = " ".join("".join(self._current_link_text).split())
            self.links.append((label, self._current_link))
            self._current_link = None
            self._current_link_text = []

    def handle_data(self, data: str) -> None:
        if self._skip_stack:
            return
        text = html.unescape(data)
        if self._current_link is not None:
            self._current_link_text.append(text)
        self.text_parts.append(text)

    def readable_text(self) -> str:
        text = "".join(self.text_parts)
        lines = [" ".join(line.split()) for line in text.splitlines()]
        return "\n".join(line for line in lines if line)


def _normalize_url(target: str) -> str:
    parsed = urllib.parse.urlparse(target)
    if parsed.scheme:
        return target
    path = Path(target)
    if path.exists():
        return path.resolve().as_uri()
    return "https://" + target


def _read_url(url: str, timeout: float = 12.0) -> tuple[str, str]:
    normalized = _normalize_url(url)
    request = urllib.request.Request(
        normalized,
        headers={"User-Agent": "Yunxi/3.0 (+local companion browser tool)"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        content_type = response.headers.get("content-type", "")
    encoding = "utf-8"
    match = re.search(r"charset=([\w.-]+)", content_type, flags=re.I)
    if match:
        encoding = match.group(1)
    try:
        return raw.decode(encoding, errors="replace"), normalized
    except LookupError:
        return raw.decode("utf-8", errors="replace"), normalized


@mcp.tool()
def browser_open(url: str) -> str:
    """Open a URL or local HTML file in the default browser."""
    normalized = _normalize_url(url)
    ok = webbrowser.open(normalized)
    if ok:
        return f"浏览器已打开：{normalized}"
    return f"浏览器打开请求已发出，但系统没有确认成功：{normalized}"


@mcp.tool()
def browser_search(query: str, engine: str = "bing", open_result: bool = False) -> str:
    """Build a search URL and optionally open it in the default browser."""
    engines = {
        "bing": "https://www.bing.com/search?q={query}",
        "google": "https://www.google.com/search?q={query}",
        "duckduckgo": "https://duckduckgo.com/?q={query}",
    }
    template = engines.get(engine.lower(), engines["bing"])
    url = template.format(query=urllib.parse.quote_plus(query))
    if open_result:
        webbrowser.open(url)
        return f"已打开搜索页：{url}"
    return f"搜索页：{url}"


@mcp.tool()
def web_page_read(url: str, max_chars: int = 6000) -> str:
    """Read a local or HTTP(S) HTML page and return readable text."""
    try:
        raw, normalized = _read_url(url)
    except Exception as exc:
        return f"[读取网页失败：{exc}]"

    parser = _ReadableHTMLParser()
    parser.feed(raw)
    text = parser.readable_text()
    if not text:
        text = raw
    text = text[: max(200, max_chars)]
    return f"来源：{normalized}\n{text}"


@mcp.tool()
def browser_extract_links(url: str, max_links: int = 30) -> str:
    """Extract links from a local or HTTP(S) HTML page."""
    try:
        raw, normalized = _read_url(url)
    except Exception as exc:
        return f"[提取链接失败：{exc}]"

    parser = _ReadableHTMLParser()
    parser.feed(raw)
    rows: list[str] = []
    for label, href in parser.links[: max(1, max_links)]:
        absolute = urllib.parse.urljoin(normalized, href)
        rows.append(f"- {label or absolute}: {absolute}")
    if not rows:
        return "没有提取到链接"
    return "\n".join(rows)


@mcp.tool()
def browser_click(url: str, link_text: str) -> str:
    """Find a link by text in a page and open it in the default browser."""
    try:
        raw, normalized = _read_url(url)
    except Exception as exc:
        return f"[点击链接失败：{exc}]"

    parser = _ReadableHTMLParser()
    parser.feed(raw)
    needle = link_text.lower()
    for label, href in parser.links:
        if needle in label.lower():
            target = urllib.parse.urljoin(normalized, href)
            webbrowser.open(target)
            return f"已打开匹配链接：{label} -> {target}"
    return f"未找到文字包含 '{link_text}' 的链接"


@mcp.tool()
def browser_type(text: str) -> str:
    """Type text into the current focused browser field."""
    if _send_keys_with_powershell(text):
        return "已向当前焦点输入文本"
    return "[浏览器输入失败：Windows SendKeys 启动失败]"


def _send_keys_with_powershell(text: str) -> bool:
    """Fallback text input through Windows Forms SendKeys."""
    import subprocess

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
