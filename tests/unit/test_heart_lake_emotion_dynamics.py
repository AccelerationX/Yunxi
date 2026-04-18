"""HeartLake 情绪动力学测试：持续性、惯性、冷却。"""

import time

import pytest

from core.cognition.heart_lake.core import HeartLake


class TestEmotionInertia:
    """情绪惯性：delta 应用系数 < 1.0，避免突变。"""

    def test_delta_scaled_by_inertia(self):
        hl = HeartLake()
        hl.emotion_inertia = 0.5  # 50% 惯性
        initial_security = hl.security
        hl.apply_emotion_delta(
            {"security": 10},
            primary_label="开心",
            confidence=1.0,
        )
        # delta 10 * inertia 0.5 = 5
        assert hl.security == pytest.approx(initial_security + 5, abs=0.1)

    def test_default_inertia_is_0_7(self):
        hl = HeartLake()
        assert hl.emotion_inertia == 0.7
        initial = hl.security
        hl.apply_emotion_delta(
            {"security": 10},
            primary_label="开心",
            confidence=1.0,
        )
        # 10 * 0.7 = 7
        assert hl.security == pytest.approx(initial + 7, abs=0.1)


class TestEmotionPersistence:
    """情绪持续性：标签切换时旧情绪保留在 compound_labels。"""

    def test_old_emotion_preserved_in_compound_labels(self):
        hl = HeartLake()
        hl.current_emotion = "平静"
        hl.apply_emotion_delta(
            {"security": -5},
            primary_label="委屈",
            compound_labels=["想念"],
        )
        assert hl.current_emotion == "委屈"
        assert "刚从平静转来" in hl.compound_labels
        assert "想念" in hl.compound_labels

    def test_persistence_fades_after_timeout(self):
        hl = HeartLake()
        hl.emotion_persistence_seconds = 0.1
        hl.current_emotion = "平静"
        # 切换到委屈，有 "刚从平静转来"
        hl.apply_emotion_delta(
            {"security": -5},
            primary_label="委屈",
        )
        assert "刚从平静转来" in hl.compound_labels
        # 等待 persistence 过期
        time.sleep(0.15)
        # 同标签再次触发，旧过渡标记不应再出现
        hl.apply_emotion_delta(
            {"security": -2},
            primary_label="委屈",
        )
        assert "刚从" not in " ".join(hl.compound_labels)
        assert hl.current_emotion == "委屈"

    def test_same_label_does_not_add_transition(self):
        hl = HeartLake()
        hl.current_emotion = "开心"
        hl.apply_emotion_delta(
            {"security": 5},
            primary_label="开心",
        )
        # 标签没变，不应有过渡标记
        assert "刚从" not in " ".join(hl.compound_labels)


class TestEmotionCooldown:
    """情绪冷却：同类型情绪短时间内再次触发时 delta 减半。"""

    def test_cooldown_reduces_delta(self):
        hl = HeartLake()
        hl.emotion_inertia = 1.0  # 关闭惯性，单独测试冷却
        initial = hl.security
        # 第一次触发
        hl.apply_emotion_delta(
            {"security": 10},
            primary_label="开心",
            confidence=1.0,
            cooldown_seconds=60.0,
        )
        first_delta = hl.security - initial
        # 立即再次触发（冷却期内）
        hl.apply_emotion_delta(
            {"security": 10},
            primary_label="开心",
            confidence=1.0,
            cooldown_seconds=60.0,
        )
        second_delta = hl.security - initial - first_delta
        # 冷却期内 delta 应减半
        assert second_delta < first_delta
        assert second_delta == pytest.approx(first_delta * 0.45, rel=0.1)

    def test_no_cooldown_after_expiry(self):
        hl = HeartLake()
        hl.emotion_inertia = 1.0
        initial = hl.security
        hl.apply_emotion_delta(
            {"security": 10},
            primary_label="开心",
            confidence=1.0,
            cooldown_seconds=0.01,
        )
        time.sleep(0.02)
        hl.apply_emotion_delta(
            {"security": 10},
            primary_label="开心",
            confidence=1.0,
            cooldown_seconds=0.01,
        )
        # 冷却过期后，两次 delta 应相同
        assert hl.security - initial == pytest.approx(20, abs=0.1)
