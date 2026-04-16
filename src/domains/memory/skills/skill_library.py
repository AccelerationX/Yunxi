"""技能库。

借鉴 15_agent_lifelong_learning 的 SkillLibrary 思想重写。
负责技能的存储、Embedding 索引、语义检索、冲突消解和成功率追踪。
"""

import asyncio
import json
import logging
import os
import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np


logger = logging.getLogger(__name__)


class OllamaSkillEmbedder:
    """Ollama /api/embeddings 接口封装，供 SkillLibrary 使用。"""

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client = None

    async def initialize(self) -> None:
        import httpx
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def encode_sync(self, texts: List[str]) -> List[List[float]]:
        """同步调用 Ollama embeddings（内部使用线程执行）。"""
        import httpx
        client = httpx.Client(base_url=self.base_url, timeout=30.0)
        try:
            embeddings: List[List[float]] = []
            for text in texts:
                response = client.post(
                    "/api/embeddings",
                    json={"model": self.model, "prompt": text},
                )
                response.raise_for_status()
                data = response.json()
                embedding = data.get("embedding", [])
                if not embedding:
                    raise RuntimeError(
                        f"Ollama embedding returned empty for model {self.model}. "
                        "Use a dedicated embedding model (e.g., nomic-embed-text)."
                    )
                embeddings.append(embedding)
            return embeddings
        finally:
            client.close()


class SkillLibrary:
    """技能库。"""

    def __init__(
        self,
        db_path: str = "data/skills/skill_library.db",
        model_name: str = "paraphrase-MiniLM-L6-v2",
        embedding_provider: Optional[str] = None,
    ):
        self.db_path = db_path
        self.model_name = model_name
        self.model = None
        self.ollama_embedder: Optional[OllamaSkillEmbedder] = None
        self.embedding_provider = embedding_provider or os.environ.get(
            "YUNXI_EMBEDDING_PROVIDER",
            "sentence_transformers",
        )
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_name TEXT UNIQUE,
                    trigger_patterns TEXT,
                    parameters TEXT,
                    actions TEXT,
                    embedding BLOB,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'approved',
                    candidate_reason TEXT DEFAULT '',
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(skills)").fetchall()}
            if "status" not in columns:
                conn.execute("ALTER TABLE skills ADD COLUMN status TEXT DEFAULT 'approved'")
            if "candidate_reason" not in columns:
                conn.execute("ALTER TABLE skills ADD COLUMN candidate_reason TEXT DEFAULT ''")

    async def initialize(self) -> None:
        """异步初始化 embedding 模型。"""
        if self.embedding_provider == "lexical":
            self.model = None
            return

        if self.embedding_provider == "ollama":
            ollama_model = os.environ.get("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
            ollama_base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            self.ollama_embedder = OllamaSkillEmbedder(model=ollama_model, base_url=ollama_base)
            await self.ollama_embedder.initialize()
            return

        from sentence_transformers import SentenceTransformer

        try:
            self.model = await asyncio.to_thread(SentenceTransformer, self.model_name)
        except Exception as exc:
            logger.warning(
                "SkillLibrary semantic model unavailable, using lexical fallback: %s",
                exc,
            )
            self.model = None

    def add_skill(self, skill: Dict[str, Any], status: str = "approved") -> None:
        """添加或更新技能。"""
        if self.model is None and self.ollama_embedder is None:
            avg_embedding = b""
        elif self.ollama_embedder is not None:
            embeddings = self.ollama_embedder.encode_sync(skill["trigger_patterns"])
            avg_embedding = np.mean(embeddings, axis=0).astype(np.float32).tobytes()
        else:
            embeddings = self.model.encode(skill["trigger_patterns"])
            avg_embedding = np.mean(embeddings, axis=0).astype(np.float32).tobytes()

        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO skills
                   (skill_name, trigger_patterns, parameters, actions, embedding, success_count, fail_count, status, candidate_reason, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?,
                           COALESCE((SELECT success_count FROM skills WHERE skill_name = ?), 0),
                           COALESCE((SELECT fail_count FROM skills WHERE skill_name = ?), 0),
                           ?,
                           ?,
                           COALESCE((SELECT created_at FROM skills WHERE skill_name = ?), ?),
                           ?)""",
                (
                    skill["skill_name"],
                    json.dumps(skill["trigger_patterns"], ensure_ascii=False),
                    json.dumps(skill["parameters"], ensure_ascii=False),
                    json.dumps(skill["actions"], ensure_ascii=False),
                    avg_embedding,
                    skill["skill_name"],
                    skill["skill_name"],
                    status,
                    str(skill.get("candidate_reason", "")),
                    skill["skill_name"],
                    now,
                    now,
                ),
            )

    def add_candidate(self, skill: Dict[str, Any], reason: str = "") -> None:
        """Store a mined skill as a pending candidate instead of enabling it."""
        candidate = dict(skill)
        candidate["candidate_reason"] = reason
        self.add_skill(candidate, status="pending")

    def list_skills(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List stored skills or candidates."""
        with sqlite3.connect(self.db_path) as conn:
            columns = self._select_columns()
            if status is None:
                rows = conn.execute(
                    f"SELECT {columns} FROM skills ORDER BY updated_at DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT {columns} FROM skills WHERE status = ? ORDER BY updated_at DESC",
                    (status,),
                ).fetchall()
        return [self._row_to_skill(row, score=0.0) for row in rows]

    def approve_candidate(self, skill_name: str) -> bool:
        """Approve a pending skill candidate so it can be used by try_skill."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE skills SET status = 'approved', updated_at = ? "
                "WHERE skill_name = ? AND status = 'pending'",
                (datetime.now().isoformat(), skill_name),
            )
            return cursor.rowcount > 0

    def reject_candidate(self, skill_name: str) -> bool:
        """Reject a pending skill candidate without deleting historical context."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE skills SET status = 'rejected', updated_at = ? "
                "WHERE skill_name = ? AND status = 'pending'",
                (datetime.now().isoformat(), skill_name),
            )
            return cursor.rowcount > 0

    async def retrieve(
        self, query: str, top_k: int = 3, threshold: float = 0.75
    ) -> List[Dict[str, Any]]:
        """根据查询语义检索最匹配的技能。"""
        query_vec = None
        if self.model is not None:
            query_vec = await asyncio.to_thread(self.model.encode, [query])
            query_vec = query_vec[0].astype(np.float32)
        elif self.ollama_embedder is not None:
            embeddings = self.ollama_embedder.encode_sync([query])
            query_vec = np.array(embeddings[0], dtype=np.float32)

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                f"SELECT {self._select_columns()} FROM skills WHERE status = 'approved'"
            ).fetchall()

        scored = []
        for row in rows:
            if query_vec is None or not row[5]:
                similarity = self._lexical_similarity(
                    query,
                    json.loads(row[2]),
                    json.loads(row[3]),
                )
            else:
                emb = np.frombuffer(row[5], dtype=np.float32)
                denominator = np.linalg.norm(query_vec) * np.linalg.norm(emb)
                similarity = 0.0 if denominator == 0 else float(np.dot(query_vec, emb) / denominator)

            success = row[6]
            fail = row[7]
            total = success + fail + 1
            success_rate = success / total

            final_score = similarity * (0.7 + 0.3 * success_rate)

            if final_score >= threshold:
                scored.append((final_score, row))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            self._row_to_skill(row, score=score)
            for score, row in scored[:top_k]
        ]

    def _row_to_skill(self, row: tuple, score: float = 0.0) -> Dict[str, Any]:
        status = row[8] if len(row) > 8 else "approved"
        candidate_reason = row[9] if len(row) > 9 else ""
        return {
            "skill_name": row[1],
            "trigger_patterns": json.loads(row[2]),
            "parameters": json.loads(row[3]),
            "actions": json.loads(row[4]),
            "score": score,
            "success_rate": row[6] / (row[6] + row[7] + 1e-6),
            "success_count": row[6],
            "fail_count": row[7],
            "status": status,
            "candidate_reason": candidate_reason,
            "created_at": row[10] if len(row) > 10 else "",
            "updated_at": row[11] if len(row) > 11 else "",
        }

    def _select_columns(self) -> str:
        return (
            "id, skill_name, trigger_patterns, parameters, actions, embedding, "
            "success_count, fail_count, status, candidate_reason, created_at, updated_at"
        )

    def _lexical_similarity(
        self,
        query: str,
        trigger_patterns: List[str],
        parameters: List[str],
    ) -> float:
        """模型不可用时的保守词面匹配分数。"""
        normalized_query = query.replace(" ", "")
        best = 0.0
        for pattern in trigger_patterns:
            normalized_pattern = pattern.replace(" ", "")
            wildcard_pattern = re.escape(normalized_pattern)
            for parameter in parameters:
                wildcard_pattern = wildcard_pattern.replace(
                    re.escape(f"{{{parameter}}}"),
                    ".+",
                )
            if re.fullmatch(wildcard_pattern, normalized_query):
                best = max(best, 0.95)
                continue

            template = normalized_pattern
            for parameter in parameters:
                template = template.replace(f"{{{parameter}}}", "")
            if template and template in normalized_query:
                best = max(best, 0.95)
            elif normalized_query and normalized_pattern:
                common_chars = set(normalized_query) & set(normalized_pattern)
                best = max(best, len(common_chars) / max(len(set(normalized_pattern)), 1))
        return best

    def record_outcome(self, skill_name: str, success: bool) -> None:
        """记录技能执行结果。"""
        column = "success_count" if success else "fail_count"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE skills SET {column} = {column} + 1 WHERE skill_name = ?",
                (skill_name,),
            )

    async def close(self) -> None:
        """释放 Ollama embedder 资源。"""
        if self.ollama_embedder is not None:
            await self.ollama_embedder.close()
            self.ollama_embedder = None
