"""经验池。

从 15_agent_lifelong_learning 借鉴经验池思想，在 yunxi3.0 内重写。
存储 Agent 的每一次工具调用和用户交互经验。
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional


class ExperienceBuffer:
    """经验池管理器。"""

    def __init__(self, db_path: str = "data/skills/experience.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experiences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    source TEXT,
                    intent_text TEXT,
                    actions TEXT,
                    outcome TEXT,
                    failure_reason TEXT,
                    metadata TEXT
                )
                """
            )

    def add(
        self,
        intent_text: str,
        actions: List[Dict[str, Any]],
        outcome: str = "success",
        source: str = "chat",
        failure_reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """添加一条经验记录。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO experiences (timestamp, source, intent_text, actions, outcome, failure_reason, metadata) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now().isoformat(),
                    source,
                    intent_text,
                    json.dumps(actions, ensure_ascii=False),
                    outcome,
                    failure_reason,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )

    def get_recent(
        self, limit: int = 1000, source: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取最近的经验记录。"""
        with sqlite3.connect(self.db_path) as conn:
            if source:
                rows = conn.execute(
                    "SELECT * FROM experiences WHERE source = ? ORDER BY timestamp DESC LIMIT ?",
                    (source, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM experiences ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()

        return [
            {
                "id": r[0],
                "timestamp": r[1],
                "source": r[2],
                "intent_text": r[3],
                "actions": json.loads(r[4]),
                "outcome": r[5],
                "failure_reason": r[6],
                "metadata": json.loads(r[7]),
            }
            for r in rows
        ]
