"""日常模式配置 — 集中管理所有硬编码阈值。

所有值优先从环境变量读取，方便根据真实使用调优。
环境变量命名规范：YUNXI_<SECTION>_<PARAM>
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


# ------------------------------------------------------------------
# HeartLake 情绪动力学配置
# ------------------------------------------------------------------

EMOTION_INERTIA: float = _env_float("YUNXI_EMOTION_INERTIA", 0.7)
"""delta 应用系数（0.0-1.0）。越低变化越渐进。"""

EMOTION_PERSISTENCE_SECONDS: float = _env_float(
    "YUNXI_EMOTION_PERSISTENCE_SECONDS", 30.0
)
"""情绪标签切换后，旧标签保留在 compound_labels 的时间。"""

EMOTION_COOLDOWN_SECONDS: float = _env_float(
    "YUNXI_EMOTION_COOLDOWN_SECONDS", 90.0
)
"""同类型情绪再次触发时的冷却期。"""

SEMANTIC_APPRAISAL_PROTECT_SECONDS: float = _env_float(
    "YUNXI_SEMANTIC_APPRAISAL_PROTECT_SECONDS", 120.0
)
"""语义评估后，感知 tick 中保护情绪标签不被 recovery 覆盖的时间。"""

RECOVERY_HALF_LIFE_SECONDS: float = _env_float(
    "YUNXI_RECOVERY_HALF_LIFE_SECONDS", 720.0
)
"""自然恢复的半衰期（约 12 分钟覆盖一半距离）。"""

# 感知 tick 想念值变化系数（每秒）
PERCEPTION_MISS_AWAY_RATE: float = 1.0 / 30.0        # away: 每 30s +1
PERCEPTION_MISS_IDLE_RATE: float = 1.0 / 60.0        # idle: 每 60s +1
PERCEPTION_MISS_WORK_RATE: float = -1.0 / 120.0      # work+fullscreen: 每 120s -1
PERCEPTION_MISS_GAME_RATE: float = 1.0 / 90.0        # game: 每 90s +1
PERCEPTION_MISS_ACTIVE_RATE: float = -1.0 / 30.0     # active: 每 30s -1
PERCEPTION_MISS_DEFAULT_RATE: float = -1.0 / 180.0   # 其他: 每 180s -1

# 感知 tick 安全感变化系数（每秒）
PERCEPTION_SECURITY_AWAY_RATE: float = -1.0 / 60.0
PERCEPTION_SECURITY_WORK_RATE: float = 1.0 / 180.0
PERCEPTION_SECURITY_ACTIVE_APART_RATE: float = -1.0 / 120.0
PERCEPTION_SECURITY_ACTIVE_TOGETHER_RATE: float = 1.0 / 60.0
PERCEPTION_SECURITY_DEFAULT_RATE: float = 1.0 / 180.0

# 感知 tick 其他维度变化系数（每秒）
PERCEPTION_TENDERNESS_WORK_NIGHT_RATE: float = 1.0 / 120.0
PERCEPTION_PLAYFULNESS_GAME_RATE: float = 1.0 / 120.0
PERCEPTION_VULNERABILITY_AWAY_LOW_SEC_RATE: float = 1.0 / 60.0

# ------------------------------------------------------------------
# InitiativeEngine 主动触发配置
# ------------------------------------------------------------------

DEFAULT_DAILY_PROACTIVE_BUDGET: int = _env_int(
    "YUNXI_DAILY_PROACTIVE_BUDGET", 5
)
"""每日主动消息预算。"""

INITIATIVE_TRIGGER_THRESHOLD: float = _env_float(
    "YUNXI_INITIATIVE_TRIGGER_THRESHOLD", 0.55
)
"""主动触发分数阈值。"""

INITIATIVE_COOLDOWN_SECONDS: float = _env_float(
    "YUNXI_INITIATIVE_COOLDOWN_SECONDS", 300.0
)
"""两次主动触发之间的最小间隔。"""

INITIATIVE_UNANSWERED_CAP: int = _env_int(
    "YUNXI_INITIATIVE_UNANSWERED_CAP", 3
)
"""未回复主动消息达到此数时完全停止主动。"""

# 事件加分
INITIATIVE_SCORE_USER_RETURNED: float = 0.55
INITIATIVE_SCORE_LONG_IDLE: float = 0.35
INITIATIVE_SCORE_APP_CHANGED: float = 0.20

# 情绪加分
INITIATIVE_SCORE_WORRIED: float = 0.45
INITIATIVE_SCORE_MISS: float = 0.30
INITIATIVE_SCORE_JEALOUS: float = 0.25

# 想念值加分阈值
INITIATIVE_MISS_HIGH_THRESHOLD: int = 85
INITIATIVE_MISS_MEDIUM_THRESHOLD: int = 70
INITIATIVE_SCORE_MISS_HIGH: float = 0.45
INITIATIVE_SCORE_MISS_MEDIUM: float = 0.30

# Presence Murmur 维度门限
PRESENCE_MURMUR_VULNERABILITY_MAX: float = 55.0
PRESENCE_MURMUR_PLAYFULNESS_MIN: float = 55.0
PRESENCE_MURMUR_INTIMACY_WARMTH_MIN: float = 66.0

# Presence Murmur 惩罚
PRESENCE_MURMUR_FULLSCREEN_PENALTY: float = -0.45
PRESENCE_MURMUR_HIGH_INPUT_PENALTY: float = -0.35
PRESENCE_MURMUR_AWAY_PENALTY: float = -0.20

# ------------------------------------------------------------------
# Runtime Presence Murmur 投递配置
# ------------------------------------------------------------------

PRESENCE_MURMUR_MAX_LENGTH: int = _env_int(
    "YUNXI_PRESENCE_MURMUR_MAX_LENGTH", 80
)
"""碎碎念最大字符数。"""

# ------------------------------------------------------------------
# 便捷访问对象
# ------------------------------------------------------------------


@dataclass(frozen=True)
class DailyModeConfig:
    """不可变的日常模式配置快照。"""

    emotion_inertia: float = EMOTION_INERTIA
    emotion_persistence_seconds: float = EMOTION_PERSISTENCE_SECONDS
    emotion_cooldown_seconds: float = EMOTION_COOLDOWN_SECONDS
    semantic_appraisal_protect_seconds: float = SEMANTIC_APPRAISAL_PROTECT_SECONDS
    recovery_half_life_seconds: float = RECOVERY_HALF_LIFE_SECONDS
    initiative_trigger_threshold: float = INITIATIVE_TRIGGER_THRESHOLD
    initiative_cooldown_seconds: float = INITIATIVE_COOLDOWN_SECONDS
    daily_proactive_budget: int = DEFAULT_DAILY_PROACTIVE_BUDGET
    presence_murmur_max_length: int = PRESENCE_MURMUR_MAX_LENGTH


def get_config() -> DailyModeConfig:
    """返回当前配置快照（环境变量实时生效）。"""
    return DailyModeConfig()
