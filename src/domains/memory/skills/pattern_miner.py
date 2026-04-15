"""模式挖掘器。

借鉴 15_agent_lifelong_learning 的 K-Means 聚类思想重写。
从 ExperienceBuffer 中发现重复出现的意图-动作模式。
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import numpy as np
from sklearn.cluster import KMeans


logger = logging.getLogger(__name__)


class PatternMiner:
    """模式挖掘器。"""

    def __init__(
        self,
        model_name: str = "paraphrase-MiniLM-L6-v2",
        embedding_provider: Optional[str] = None,
    ):
        self.model_name = model_name
        self.model = None
        self.embedding_provider = embedding_provider or os.environ.get(
            "YUNXI_EMBEDDING_PROVIDER",
            "sentence_transformers",
        )

    async def initialize(self) -> None:
        """异步初始化 Sentence-BERT 模型（避免阻塞事件循环）。"""
        if self.embedding_provider == "lexical":
            self.model = None
            return

        from sentence_transformers import SentenceTransformer

        try:
            self.model = await asyncio.to_thread(SentenceTransformer, self.model_name)
        except Exception as exc:
            logger.warning(
                "PatternMiner semantic model unavailable, using lexical fallback: %s",
                exc,
            )
            self.model = None

    async def mine(
        self, experiences: List[Dict[str, Any]], min_cluster_size: int = 3
    ) -> List[Dict[str, Any]]:
        """从经验记录中挖掘重复模式。"""
        if len(experiences) < min_cluster_size:
            return []

        if self.model is None:
            return self._mine_by_lexical_groups(experiences, min_cluster_size)

        texts = [e["intent_text"] for e in experiences]
        embeddings = await asyncio.to_thread(self.model.encode, texts)
        embeddings = np.array(embeddings)

        n = len(experiences)
        k = min(max(2, int(np.sqrt(n))), n // min_cluster_size)

        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = await asyncio.to_thread(kmeans.fit_predict, embeddings)

        patterns = []
        for cluster_id in range(k):
            cluster_indices = np.where(labels == cluster_id)[0]
            if len(cluster_indices) < min_cluster_size:
                continue

            cluster_exps = [experiences[i] for i in cluster_indices]

            center = kmeans.cluster_centers_[cluster_id]
            distances = np.linalg.norm(embeddings[cluster_indices] - center, axis=1)
            representative_idx = cluster_indices[np.argmin(distances)]
            representative_intent = experiences[representative_idx]["intent_text"]

            success_actions = next(
                (e["actions"] for e in cluster_exps if e["outcome"] == "success"),
                cluster_exps[0]["actions"],
            )

            # 使用余弦相似度计算聚类内紧密度（更稳定）
            center_norm = center / (np.linalg.norm(center) + 1e-9)
            cluster_embs = embeddings[cluster_indices]
            norms = np.linalg.norm(cluster_embs, axis=1, keepdims=True) + 1e-9
            cos_sims = np.dot(cluster_embs / norms, center_norm)
            confidence = float(np.mean(cos_sims))

            patterns.append({
                "cluster_id": int(cluster_id),
                "size": len(cluster_indices),
                "representative_intent": representative_intent,
                "actions": success_actions,
                "confidence": confidence,
            })

        patterns.sort(key=lambda x: x["confidence"], reverse=True)
        return patterns

    def _mine_by_lexical_groups(
        self,
        experiences: List[Dict[str, Any]],
        min_cluster_size: int,
    ) -> List[Dict[str, Any]]:
        """模型不可用时按意图关键词做保守聚类。"""
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for experience in experiences:
            key = self._intent_group_key(experience.get("intent_text", ""))
            groups.setdefault(key, []).append(experience)

        patterns: List[Dict[str, Any]] = []
        for group_key, group_experiences in groups.items():
            if len(group_experiences) < min_cluster_size:
                continue
            success_actions = next(
                (
                    e["actions"]
                    for e in group_experiences
                    if e.get("outcome") == "success"
                ),
                group_experiences[0]["actions"],
            )
            patterns.append(
                {
                    "cluster_id": len(patterns),
                    "size": len(group_experiences),
                    "representative_intent": group_experiences[0]["intent_text"],
                    "actions": success_actions,
                    "confidence": 0.55,
                    "fallback_group": group_key,
                }
            )
        return patterns

    def _intent_group_key(self, intent: str) -> str:
        """将常见意图映射到稳定的保守分组。"""
        if any(word in intent for word in ("天气", "温度", "下雨")):
            return "weather"
        if "计算" in intent:
            return "calculate"
        if "打开" in intent:
            return "launch_application"
        if any(word in intent for word in ("剪贴板", "复制", "粘贴")):
            return "clipboard"
        if "截图" in intent:
            return "screenshot"
        return intent[:8]
