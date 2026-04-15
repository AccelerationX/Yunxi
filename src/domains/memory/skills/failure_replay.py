"""失败回放。

借鉴 15_agent_lifelong_learning 的失败回放思想重写。
记录历史失败场景，并在后续相似请求中注入注意事项。
"""

import sqlite3
from datetime import datetime
from typing import List, Optional


class FailureReplay:
    """失败回放管理器。"""

    def __init__(self, db_path: str = "data/skills/failures.db"):
        self.db_path = db_path
        import os

        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    context_keywords TEXT,
                    tool_name TEXT,
                    intent_summary TEXT,
                    failure_reason TEXT,
                    suggestion TEXT
                )
                """
            )

    def record(
        self,
        intent_summary: str,
        tool_name: str,
        failure_reason: str,
        suggestion: str = "",
        context_keywords: Optional[List[str]] = None,
    ) -> None:
        """记录一次失败场景。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO failures (timestamp, context_keywords, tool_name, intent_summary, failure_reason, suggestion) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    datetime.now().isoformat(),
                    ",".join(context_keywords or []),
                    tool_name,
                    intent_summary,
                    failure_reason,
                    suggestion,
                ),
            )

    def clear(self) -> None:
        """清空所有失败记录。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM failures")

    def retrieve(
        self, current_intent: str, current_tools: Optional[List[str]] = None, limit: int = 3
    ) -> List[str]:
        """检索与当前意图和工具相关的历史失败注意事项。"""
        keywords = set(current_intent.lower().split())
        if current_tools:
            keywords |= {t.lower() for t in current_tools}

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM failures ORDER BY timestamp DESC"
            ).fetchall()

        matched = []
        for row in rows:
            context_keywords = set(row[2].lower().split(",")) if row[2] else set()
            tool_name = row[3].lower()
            suggestion = row[6] or row[5]
            overlap = len(keywords & context_keywords) + (1 if tool_name in keywords else 0)
            # fallback: substring match for Chinese keywords without spaces
            if overlap == 0:
                for kw in keywords:
                    if any(kw in ck for ck in context_keywords) or kw in suggestion:
                        overlap = 1
                        break
            if overlap > 0:
                matched.append((overlap, suggestion))

        matched.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in matched[:limit]]
