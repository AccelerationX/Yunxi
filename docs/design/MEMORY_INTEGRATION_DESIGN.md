# 云汐 3.0 记忆系统接入修复设计文档（融合终身学习版）

> **定位**：修复记忆系统与主链路（LLM Prompt / 执行引擎）的断裂，并深度融合 `15_agent_lifelong_learning` 的研究成果，让云汐从长期交互中自动发现模式、提炼技能、避免重复犯错。  
> **核心原则**：记忆不是被动的"记账员"，而是对话上下文的有机组成部分；技能是记忆的升华，能直接驱动行为。

---

## 一、设计目标

1. **统一接口**：`MemoryManager` 必须能被 `YunxiExecutionEngine` 和 `YunxiPromptBuilder` 直接调用。
2. **读写闭环**：对话开始时可以读取记忆摘要注入 prompt；对话结束时自动归档为 episode。
3. **技能自动发现**：从 MCP 审计日志和对话历史中自动挖掘重复模式，抽象为可执行技能模板。
4. **失败回放**：历史失败经验作为注意事项注入 Prompt，提升容错能力。
5. **保留 2.0 存储层**：不改 SQLite/JSON 存储实现，只修复"读取和注入"的链路，并新增 SkillLibrary。

---

## 二、研究成果借鉴与重写声明

### 2.1 借鉴 `15_agent_lifelong_learning`

**借鉴内容**：
- `ExperienceBuffer`（SQLite 经验池）结构
- `PatternMiner`（Sentence-BERT + K-Means 聚类）的自动模式发现思路
- `SkillDistiller`（将具体经验抽象为参数化技能模板）
- `SkillLibrary`（Embedding 索引 + 语义检索 + 冲突消解 + 成功率追踪）
- `FailureReplay`（历史注意事项注入）
- `ParamFiller`（从请求中提取参数值）

**重写声明**：
- 不在 yunxi3.0 中 import `ResearchProjects/15_agent_lifelong_learning/` 的任何文件。
- 在 `yunxi3.0/domains/memory/skills/` 目录下重写 `experience_buffer.py`、`pattern_miner.py`、`skill_distiller.py`、`skill_library.py`、`failure_replay.py`、`param_filler.py`。
- 接口设计会根据 yunxi3.0 的 asyncio 架构和 HeartLake 情感状态上下文重新设计。

---

## 三、增强后的记忆系统架构

```
对话经验 / MCP 审计日志 (audit.jsonl)
        ↓
┌─────────────────────┐
│   ExperienceBuffer  │  ← SQLite 经验池
│   (经验记录与清洗)    │
└──────────┬──────────┘
           ↓ 每日后台扫描
┌─────────────────────┐
│    PatternMiner     │  ← Sentence-BERT + K-Means
│   (重复模式发现)      │
└──────────┬──────────┘
           ↓ (置信度 > 0.8)
┌─────────────────────┐
│   SkillDistiller    │  ← LLM / 规则泛化
│   (技能模板生成)      │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│    SkillLibrary     │  ← SQLite + Embedding 索引
│   (技能存储与检索)    │
└──────────┬──────────┘
           ↓ 高匹配度时
    ┌──────┴──────┐
    ↓             ↓
┌────────┐   ┌────────────┐
│Macro执行│   │ LLM 通用推理 │
│(快速路径)│   │ (慢速路径)   │
└────────┘   └────────────┘
```

---

## 四、核心模块设计（全部在 yunxi3.0 内重写）

### 4.1 ExperienceBuffer（经验池）

```python
# domains/memory/skills/experience_buffer.py
import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any

class ExperienceBuffer:
    """
    从 15_agent_lifelong_learning 借鉴经验池思想，在 yunxi3.0 内重写。
    存储 Agent 的每一次工具调用和用户交互经验。
    """
    def __init__(self, db_path: str = "data/skills/experience.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS experiences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    source TEXT,           -- 'mcp_audit' / 'chat'
                    intent_text TEXT,      -- 用户意图或触发上下文
                    actions TEXT,          -- JSON 数组，记录执行的动作序列
                    outcome TEXT,          -- 'success' / 'failure'
                    failure_reason TEXT,   -- 失败原因（如有）
                    metadata TEXT          -- JSON 附加信息
                )
            """)
    
    def add(self, intent_text: str, actions: List[Dict], outcome: str = "success",
            source: str = "chat", failure_reason: str = "", metadata: Dict = None):
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
                )
            )
    
    def get_recent(self, limit: int = 1000, source: str = None) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            if source:
                rows = conn.execute(
                    "SELECT * FROM experiences WHERE source = ? ORDER BY timestamp DESC LIMIT ?",
                    (source, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM experiences ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
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
```

### 4.2 PatternMiner（模式挖掘）

```python
# domains/memory/skills/pattern_miner.py
from typing import List, Dict, Any, Tuple
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans

class PatternMiner:
    """
    借鉴 15_agent_lifelong_learning 的 K-Means 聚类思想重写。
    从 ExperienceBuffer 中发现重复出现的意图-动作模式。
    """
    def __init__(self, model_name: str = "paraphrase-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
    
    def mine(self, experiences: List[Dict[str, Any]], min_cluster_size: int = 3) -> List[Dict[str, Any]]:
        if len(experiences) < min_cluster_size:
            return []
        
        # 1. 提取意图文本并编码
        texts = [e["intent_text"] for e in experiences]
        embeddings = self.model.encode(texts)
        
        # 2. 自动选择 K 值（简化版：sqrt(n) 向上取整，至少 2 类）
        n = len(experiences)
        k = min(max(2, int(np.sqrt(n))), n // min_cluster_size)
        
        # 3. K-Means 聚类
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(embeddings)
        
        # 4. 筛选有效聚类
        patterns = []
        for cluster_id in range(k):
            cluster_indices = np.where(labels == cluster_id)[0]
            if len(cluster_indices) < min_cluster_size:
                continue
            
            cluster_exps = [experiences[i] for i in cluster_indices]
            
            # 计算聚类中心最近样本作为代表意图
            center = kmeans.cluster_centers_[cluster_id]
            distances = np.linalg.norm(embeddings[cluster_indices] - center, axis=1)
            representative_idx = cluster_indices[np.argmin(distances)]
            representative_intent = experiences[representative_idx]["intent_text"]
            
            # 统计最常见的动作序列（简化：取第一个成功样本的动作序列）
            success_actions = next(
                (e["actions"] for e in cluster_exps if e["outcome"] == "success"),
                cluster_exps[0]["actions"]
            )
            
            patterns.append({
                "cluster_id": int(cluster_id),
                "size": len(cluster_indices),
                "representative_intent": representative_intent,
                "actions": success_actions,
                "confidence": float(1.0 - np.mean(distances)),  # 聚类内聚度越高，置信度越高
            })
        
        # 按置信度排序
        patterns.sort(key=lambda x: x["confidence"], reverse=True)
        return patterns
```

### 4.3 SkillDistiller（技能蒸馏器）

```python
# domains/memory/skills/skill_distiller.py
import re
from typing import Dict, Any, List

class SkillDistiller:
    """
    借鉴 15_agent_lifelong_learning 的技能抽象思想重写。
    将 PatternMiner 发现的模式泛化为带参数的技能模板。
    """
    def distill(self, pattern: Dict[str, Any]) -> Dict[str, Any]:
        intent = pattern["representative_intent"]
        actions = pattern["actions"]
        
        # 1. 尝试从意图中提取参数占位符
        params = self._extract_params(intent)
        
        # 2. 泛化 trigger patterns
        triggers = self._generalize_triggers(intent, params)
        
        # 3. 构建技能定义
        skill = {
            "skill_name": self._generate_skill_name(intent),
            "trigger_patterns": triggers,
            "parameters": list(params.keys()),
            "actions": actions,  # 动作序列中的参数值后续由 ParamFiller 填充
            "source_pattern": pattern,
            "version": 1,
        }
        
        return skill
    
    def _extract_params(self, intent: str) -> Dict[str, str]:
        """从意图中提取可能的参数占位符"""
        params = {}
        
        # 股票代码
        stock_match = re.search(r'([\u4e00-\u9fa5]{2,4})', intent)
        if stock_match:
            params["stock_name"] = stock_match.group(1)
        
        # 城市名（天气查询）
        city_match = re.search(r'(.+?)的?(天气|温度)', intent)
        if city_match:
            params["city"] = city_match.group(1)
        
        # 数学表达式
        math_match = re.search(r'计算\s*([\d\+\-\*\/\(\)\.]+)', intent)
        if math_match:
            params["expression"] = math_match.group(1)
        
        # 应用名（桌面操作）
        app_match = re.search(r'打开\s*(.+?)(?:$|并|然后)', intent)
        if app_match:
            params["app_name"] = app_match.group(1).strip()
        
        return params
    
    def _generalize_triggers(self, intent: str, params: Dict[str, str]) -> List[str]:
        """生成泛化的触发模式"""
        triggers = [intent]
        
        # 替换具体参数为占位符，生成模板化触发词
        generalized = intent
        for key, value in params.items():
            generalized = generalized.replace(value, f"{{{key}}}")
        
        if generalized != intent:
            triggers.append(generalized)
        
        return triggers
    
    def _generate_skill_name(self, intent: str) -> str:
        """基于意图生成技能名称"""
        if "天气" in intent:
            return "query_weather"
        elif "计算" in intent:
            return "calculate_expression"
        elif "打开" in intent:
            return "launch_application"
        elif "截图" in intent:
            return "capture_screenshot"
        elif "剪贴板" in intent or "复制" in intent:
            return "clipboard_operation"
        else:
            # 默认：取前 3 个关键词
            words = intent.replace("，", " ").replace("。", " ").split()[:3]
            return "_".join(words) or "unknown_skill"
```

### 4.4 SkillLibrary（技能库）

```python
# domains/memory/skills/skill_library.py
import sqlite3
import json
import os
import numpy as np
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any, Optional

class SkillLibrary:
    """
    借鉴 15_agent_lifelong_learning 的 SkillLibrary 思想重写。
    负责技能的存储、Embedding 索引、语义检索、冲突消解和成功率追踪。
    """
    def __init__(self, db_path: str = "data/skills/skill_library.db",
                 model_name: str = "paraphrase-MiniLM-L6-v2"):
        self.db_path = db_path
        self.model = SentenceTransformer(model_name)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_name TEXT UNIQUE,
                    trigger_patterns TEXT,
                    parameters TEXT,
                    actions TEXT,
                    embedding BLOB,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
    
    def add_skill(self, skill: Dict[str, Any]):
        """添加或更新技能"""
        # 计算 trigger patterns 的平均 embedding
        embeddings = self.model.encode(skill["trigger_patterns"])
        avg_embedding = np.mean(embeddings, axis=0).astype(np.float32).tobytes()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO skills 
                   (skill_name, trigger_patterns, parameters, actions, embedding, success_count, fail_count, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 
                           COALESCE((SELECT success_count FROM skills WHERE skill_name = ?), 0),
                           COALESCE((SELECT fail_count FROM skills WHERE skill_name = ?), 0),
                           COALESCE((SELECT created_at FROM skills WHERE skill_name = ?), ?),
                           ?)""",
                (
                    skill["skill_name"],
                    json.dumps(skill["trigger_patterns"], ensure_ascii=False),
                    json.dumps(skill["parameters"], ensure_ascii=False),
                    json.dumps(skill["actions"], ensure_ascii=False),
                    avg_embedding,
                    skill["skill_name"], skill["skill_name"], skill["skill_name"],
                    skill.get("created_at", ""),
                    skill.get("updated_at", ""),
                )
            )
    
    def retrieve(self, query: str, top_k: int = 3, threshold: float = 0.75) -> List[Dict[str, Any]]:
        """根据查询语义检索最匹配的技能"""
        query_vec = self.model.encode([query])[0].astype(np.float32)
        
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM skills").fetchall()
        
        scored = []
        for row in rows:
            emb = np.frombuffer(row[5], dtype=np.float32)
            similarity = float(np.dot(query_vec, emb) / (np.linalg.norm(query_vec) * np.linalg.norm(emb)))
            
            # 成功率加权
            success = row[6]
            fail = row[7]
            total = success + fail + 1
            success_rate = success / total
            
            final_score = similarity * (0.7 + 0.3 * success_rate)
            
            if final_score >= threshold:
                scored.append((final_score, row))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        
        return [
            {
                "skill_name": row[1],
                "trigger_patterns": json.loads(row[2]),
                "parameters": json.loads(row[3]),
                "actions": json.loads(row[4]),
                "score": score,
                "success_rate": row[6] / (row[6] + row[7] + 1e-6),
            }
            for score, row in scored[:top_k]
        ]
    
    def record_outcome(self, skill_name: str, success: bool):
        """记录技能执行结果，用于成功率追踪"""
        column = "success_count" if success else "fail_count"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE skills SET {column} = {column} + 1 WHERE skill_name = ?",
                (skill_name,)
            )
```

### 4.5 FailureReplay（失败回放）

```python
# domains/memory/skills/failure_replay.py
import sqlite3
import os
import json
from typing import List, Dict, Any

class FailureReplay:
    """
    借鉴 15_agent_lifelong_learning 的失败回放思想重写。
    记录历史失败场景，并在后续相似请求中注入注意事项。
    """
    def __init__(self, db_path: str = "data/skills/failures.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    context_keywords TEXT,  -- 逗号分隔的关键词，用于快速匹配
                    tool_name TEXT,
                    intent_summary TEXT,
                    failure_reason TEXT,
                    suggestion TEXT         -- 建议的注意事项
                )
            """)
    
    def record(self, intent_summary: str, tool_name: str, failure_reason: str,
               suggestion: str = "", context_keywords: List[str] = None):
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
                )
            )
    
    def retrieve(self, current_intent: str, current_tools: List[str], limit: int = 3) -> List[str]:
        """检索与当前意图和工具相关的历史失败注意事项"""
        # 简单关键词匹配（可后续升级为 embedding 匹配）
        keywords = set(current_intent.lower().split()) | set(t.lower() for t in current_tools)
        
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM failures ORDER BY timestamp DESC"
            ).fetchall()
        
        matched = []
        for row in rows:
            context_keywords = set(row[3].lower().split(",")) if row[3] else set()
            tool_name = row[4].lower()
            overlap = len(keywords & context_keywords) + (1 if tool_name in keywords else 0)
            if overlap > 0:
                suggestion = row[7] or row[6]
                matched.append((overlap, suggestion))
        
        matched.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in matched[:limit]]
```

### 4.6 ParamFiller（参数填充器）

```python
# domains/memory/skills/param_filler.py
import re
from typing import Dict, Any

class ParamFiller:
    """
    借鉴 15_agent_lifelong_learning 的参数填充思想重写。
    从用户请求中提取技能模板所需的具体参数值。
    """
    def fill(self, request: str, skill: Dict[str, Any]) -> Dict[str, str]:
        params = {}
        for param in skill.get("parameters", []):
            value = self._extract_param(request, param)
            if value:
                params[param] = value
        return params
    
    def _extract_param(self, request: str, param_name: str) -> str:
        rules = {
            "city": r'(.+?)的?(天气|温度|下雨)',
            "stock_name": r'([\u4e00-\u9fa5]{2,4})',
            "expression": r'计算\s*([\d\+\-\*\/\(\)\.]+)',
            "app_name": r'打开\s*(.+?)(?:$|并|然后|再)',
            "file_path": r'([A-Za-z]:\\[^\s]+|\/[^\s]+)',
            "url": r'(https?://[^\s]+)',
        }
        
        pattern = rules.get(param_name)
        if pattern:
            match = re.search(pattern, request)
            if match:
                return match.group(1).strip()
        
        return ""
```

---

## 五、增强后的 MemoryManager

```python
# domains/memory/manager.py（在 2.0 基础上新增 SkillSubsystem）
class MemoryManager:
    def __init__(self, base_path: str = "data/memory"):
        # ... 保留 2.0 的 semantic / episodic / autobiographical / perceptual / working 初始化 ...
        
        # 3.0 新增：终身学习子系统
        self.experience_buffer = ExperienceBuffer(
            db_path=os.path.join(base_path, "skills", "experience.db")
        )
        self.pattern_miner = PatternMiner()
        self.skill_distiller = SkillDistiller()
        self.skill_library = SkillLibrary(
            db_path=os.path.join(base_path, "skills", "skill_library.db")
        )
        self.failure_replay = FailureReplay(
            db_path=os.path.join(base_path, "skills", "failures.db")
        )
        self.param_filler = ParamFiller()
    
    # ==================== 原有接口增强 ====================
    
    def get_summary(self, max_lines: int = 8) -> str:
        parts = []
        
        # 1. 用户偏好
        preferences = self._get_preferences_summary(limit=3)
        if preferences:
            parts.append(f"远的喜好：{preferences}")
        
        # 2. 最近发生的事
        recent = self._get_episodes_summary(limit=3)
        if recent:
            parts.append(f"最近的事：{recent}")
        
        # 3. 未完成的小约定
        promises = self._get_promises_summary(limit=2)
        if promises:
            parts.append(f"你们的小约定：{promises}")
        
        # 4. 上一次对话主题
        last_topic = self._get_last_topic()
        if last_topic:
            parts.append(f"上次聊到了：{last_topic}")
        
        return "；".join(parts[:max_lines])
    
    def get_failure_hints(self, current_intent: str, current_tools: List[str]) -> str:
        """获取失败回放中的注意事项，用于 Prompt 注入"""
        hints = self.failure_replay.retrieve(current_intent, current_tools, limit=3)
        if not hints:
            return ""
        return "\n".join([f"- 注意：{h}" for h in hints])
    
    # ==================== 技能系统接口 ====================
    
    def try_skill(self, user_input: str) -> Optional[Dict[str, Any]]:
        """
        尝试用技能匹配用户请求。
        如果匹配度高且参数填充成功，返回可直接执行的技能动作序列。
        否则返回 None，走通用 LLM 推理。
        """
        matches = self.skill_library.retrieve(user_input, top_k=1, threshold=0.80)
        if not matches:
            return None
        
        skill = matches[0]
        params = self.param_filler.fill(user_input, skill)
        
        # 如果还有未填充的参数，暂时不走技能路径
        missing = [p for p in skill["parameters"] if p not in params or not params[p]]
        if missing:
            return None
        
        # 参数化替换动作序列
        actions = []
        for action in skill["actions"]:
            filled_action = {
                "tool": action["tool"],
                "args": {k: v.format(**params) for k, v in action["args"].items()},
            }
            actions.append(filled_action)
        
        return {
            "skill_name": skill["skill_name"],
            "actions": actions,
            "parameters": params,
        }
    
    def record_skill_outcome(self, skill_name: str, success: bool):
        """记录技能执行结果"""
        self.skill_library.record_outcome(skill_name, success)
    
    def record_experience(self, intent_text: str, actions: List[Dict], outcome: str,
                          source: str = "chat", failure_reason: str = "", metadata: Dict = None):
        """记录经验到 ExperienceBuffer"""
        self.experience_buffer.add(
            intent_text=intent_text,
            actions=actions,
            outcome=outcome,
            source=source,
            failure_reason=failure_reason,
            metadata=metadata,
        )
    
    async def run_skill_learning_cycle(self):
        """
        后台学习周期（建议每晚运行一次）。
        从 ExperienceBuffer 中挖掘模式，蒸馏为技能，存入 SkillLibrary。
        """
        experiences = self.experience_buffer.get_recent(limit=500, source="mcp_audit")
        if len(experiences) < 3:
            return
        
        patterns = self.pattern_miner.mine(experiences, min_cluster_size=3)
        
        for pattern in patterns:
            # 只将高置信度模式转为技能
            if pattern["confidence"] < 0.8:
                continue
            
            skill = self.skill_distiller.distill(pattern)
            
            # 检查是否已有同名技能，如有则版本升级
            existing = self.skill_library.retrieve(skill["skill_name"], top_k=1, threshold=0.99)
            if existing and existing[0]["skill_name"] == skill["skill_name"]:
                skill["version"] = existing[0].get("version", 1) + 1
            
            self.skill_library.add_skill(skill)
```

---

## 六、PromptBuilder 与执行引擎的适配

### 6.1 PromptBuilder 新增 FailureReplay Section

```python
# core/prompt_builder.py（_build_memory_section 增强）

def _build_memory_section(self, context: RuntimeContext) -> str:
    parts = []
    
    # 原有记忆摘要
    if context.memory_summary:
        parts.append(f"【你们共同的记忆】\n{context.memory_summary}")
    
    # 新增：失败回放注意事项
    if context.failure_hints:
        parts.append(f"【历史经验提醒】\n{context.failure_hints}")
    
    return "\n\n".join(parts)
```

### 6.2 执行引擎的 Skill 快速路径

```python
# core/execution/engine.py（respond 方法中增加 skill 检查）

async def respond(self, user_input: str, system_prompt: str) -> ExecutionResult:
    self.context.add_user_message(user_input)
    
    # ===== 新增：技能快速路径 =====
    skill_match = self.memory.try_skill(user_input)
    if skill_match:
        # 直接执行技能动作序列（通过 MCP Hub）
        results = []
        for action in skill_match["actions"]:
            # 通过 MCP Hub 执行单个工具
            result = await self.mcp_hub.execute_single(action["tool"], action["args"], self.runtime_context)
            results.append(result)
        
        # 构建回复
        response_text = f"好的，已经帮你完成啦～ ({skill_match['skill_name']})"
        self.memory.record_skill_outcome(skill_match["skill_name"], success=True)
        self.memory.record_experience(user_input, skill_match["actions"], "success")
        self.context.add_assistant_message(response_text)
        return ExecutionResult(content=response_text)
    
    # ===== 原有 LLM 路径 =====
    # ... 调用 LLM ...
```

---

## 七、经验输入源设计

### 7.1 MCP 审计日志自动导入

```python
# 在 core/mcp/audit_logger.py 中增加回调

class AuditLogger:
    def __init__(self, log_dir: str = "logs/mcp_audit", memory_manager=None):
        self.log_dir = log_dir
        self.memory_manager = memory_manager  # 3.0 新增
    
    async def record(self, plan, results, security_decisions) -> str:
        # ... 原有日志写入 ...
        
        # 同时写入 ExperienceBuffer
        if self.memory_manager:
            intent = self._infer_intent_from_plan(plan)
            actions = [{"tool": p.tool_name, "args": p.arguments} for p in plan]
            all_success = all(not r.get("is_error", False) for r in results)
            failure_reason = ""
            if not all_success:
                failure_reason = "; ".join(
                    r.get("error", "") for r in results if r.get("is_error")
                )
            
            self.memory_manager.record_experience(
                intent_text=intent,
                actions=actions,
                outcome="success" if all_success else "failure",
                source="mcp_audit",
                failure_reason=failure_reason,
            )
        
        return log_id
```

### 7.2 对话经验记录

每次 `YunxiRuntime.chat()` 结束后：
```python
self.memory.record_experience(
    intent_text=user_input,
    actions=[{"type": "chat_response", "content": result.content}],
    outcome="success" if not result.error else "failure",
    source="chat",
    failure_reason=result.error or "",
)
```

---

## 八、实施步骤

### Step 1：建立 `domains/memory/skills/` 目录
- 依次实现 `experience_buffer.py`、`pattern_miner.py`、`skill_distiller.py`、`skill_library.py`、`failure_replay.py`、`param_filler.py`。

### Step 2：增强 `MemoryManager`
- 在 `__init__` 中初始化终身学习子系统。
- 新增 `try_skill()`、`record_skill_outcome()`、`record_experience()`、`run_skill_learning_cycle()`、`get_failure_hints()`。

### Step 3：修改 `AuditLogger`
- 增加 `memory_manager` 引用，在每次记录审计日志时同步写入 `ExperienceBuffer`。

### Step 4：修改 `YunxiPromptBuilder`
- `RuntimeContext` 新增 `failure_hints` 字段。
- `_build_memory_section()` 中追加失败回放注意事项。

### Step 5：修改 `YunxiExecutionEngine`
- 在 `respond()` 开头增加 `try_skill()` 快速路径检查。

### Step 6：设置后台学习定时任务
- 在 daemon 的 `SchedulerService` 或 `YunxiPresence` 的 tick 循环中，每天凌晨调用一次 `memory.run_skill_learning_cycle()`。

### Step 7：测试验证
- 通过 `ConversationTester` 模拟重复请求，验证技能是否被自动发现并后续直接命中。
- 验证失败后再次请求相同场景时，`FailureReplay` 的提示是否出现在 Prompt 中。

---

## 九、验收标准

1. `ExperienceBuffer` 能正确记录 MCP 审计日志和对话经验。
2. 连续 3 次相似的 MCP 调用（如"查深圳天气"）后，`PatternMiner` 能挖掘出对应模式。
3. `SkillDistiller` 能将模式泛化为带 `{city}` 参数的 `query_weather` 技能。
4. `SkillLibrary` 能对该技能的后续查询实现 > 0.8 的匹配度检索。
5. 当用户再次说"帮我查一下北京天气"时，`try_skill()` 成功匹配并直接通过 MCP Hub 执行，不经过通用 LLM 推理。
6. 某工具调用失败后（如 `window_focus_ui` 在全屏游戏上失败），`FailureReplay` 记录该失败；后续相似请求时，Prompt 中出现"注意：上次尝试聚焦全屏窗口失败"的提示。
7. 通过 `ConversationTester` 验证：技能执行成功后，记忆系统能正确记录结果并更新成功率。

---

*文档创建时间：2026-04-14*  
*最后更新时间：2026-04-14*  
*版本：v2.0*
