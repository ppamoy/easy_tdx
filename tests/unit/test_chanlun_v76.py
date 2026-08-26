"""V76 缠论模型增强测试 — 条件236-239"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from easy_tdx.chanlun.mmd import (
    _calc_price_structure_integrity_v76,
    _calc_trend_alignment_validation_v76,
    _calc_volatility_adaptive_confidence_v76,
    _calc_signal_final_validity_v76,
)
from easy_tdx.chanlun.types import MMD, MMDType
from easy_tdx.backtest.chanlun_validator import ConditionGroup


def _make_mmd(mmd_type: str = "3buy", confidence: float = 0.6) -> MMD:
    """Helper to create MMD with correct enum value."""
    return MMD(mmd_type=MMDType(mmd_type), confidence=confidence, msg="test")


def _make_closes(n: int = 100, base: float = 100.0) -> list[float]:
    import random
    random.seed(42)
    return [base + random.uniform(-5, 5) * (i / n) for i in range(n)]


class TestV76ConditionGroup:
    """V76 枚举和条件范围验证"""

    def test_v76_exists(self):
        assert hasattr(ConditionGroup, "V76")
        assert ConditionGroup.V76.value == "v76"

    def test_v76_condition_range(self):
        r = ConditionGroup.V76.condition_range
        assert r == (236, 239)

    def test_v76_description(self):
        desc = ConditionGroup.V76.description
        assert len(desc) > 0


class TestV76MMDFields:
    """MMD 对象包含 V76 字段"""

    def test_mmd_has_v76_fields(self):
        mmd = _make_mmd()
        assert hasattr(mmd, "_price_structure_integrity_v76")
        assert hasattr(mmd, "_trend_alignment_validation_v76")
        assert hasattr(mmd, "_volatility_adaptive_confidence_v76")
        assert hasattr(mmd, "_signal_final_validity_v76")


class TestV76BacktestValidator:
    """V76 回测验证框架"""

    def test_v76_in_all_groups(self):
        """V76 应在所有 ConditionGroup 列表中"""
        from easy_tdx.backtest.chanlun_validator import ConditionGroup
        all_groups = [g for g in ConditionGroup]
        assert ConditionGroup.V76 in all_groups

    def test_v76_condition_count(self):
        """V76 应有 4 个条件（236-239）"""
        start, end = ConditionGroup.V76.condition_range
        assert start == 236
        assert end == 239
        assert end - start + 1 == 4


class TestV76Functions:
    """V76 四个计算函数单元测试"""

    # --- 条件236: 价格结构完整性 ---

    def test_psi_buy_low_position(self):
        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(100, 100.0)
        closes[-1] = min(closes) * 1.01  # 价格在低位
        result = _calc_price_structure_integrity_v76(mmd, closes, None)
        assert result["structure_score"] > 0
        assert isinstance(result["trend_structure"], str)
        assert isinstance(result["confirm_signal"], bool)
        assert isinstance(result["confidence_adjust"], float)

    def test_psi_sell_high_position(self):
        mmd = _make_mmd("3sell", 0.6)
        closes = _make_closes(100, 100.0)
        closes[-1] = max(closes) * 0.99  # 价格在高位
        result = _calc_price_structure_integrity_v76(mmd, closes, None)
        assert result["structure_score"] > 0
        assert isinstance(result["trend_structure"], str)

    def test_psi_insufficient_data(self):
        mmd = _make_mmd()
        result = _calc_price_structure_integrity_v76(mmd, [1.0, 2.0], None)
        assert "数据不足" in result["msg"]
        assert result["structure_score"] == 0.0

    def test_psi_with_volume_confirmation(self):
        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(100, 100.0)
        volumes = [1000.0] * 100
        volumes[-1] = 1500.0  # 放量
        closes[-1] = min(closes) * 1.01
        result = _calc_price_structure_integrity_v76(mmd, closes, volumes)
        assert result["structure_score"] >= 0.3

    # --- 条件237: 趋势方向对齐 ---

    def test_tav_bullish_alignment(self):
        mmd = _make_mmd("3buy", 0.6)
        closes = [100.0 + i * 0.5 for i in range(100)]  # 上升趋势
        result = _calc_trend_alignment_validation_v76(mmd, closes)
        assert result["alignment_status"] in (
            "strong_aligned", "moderately_aligned", "diverged", "unknown"
        )
        assert result["trend_direction"] in (
            "bullish", "weak_bullish", "bearish", "weak_bearish", "neutral"
        )

    def test_tav_bearish_alignment(self):
        mmd = _make_mmd("3sell", 0.6)
        closes = [100.0 - i * 0.5 for i in range(100)]  # 下降趋势
        result = _calc_trend_alignment_validation_v76(mmd, closes)
        assert result["trend_direction"] in (
            "bullish", "weak_bullish", "bearish", "weak_bearish", "neutral"
        )

    def test_tav_insufficient_data(self):
        mmd = _make_mmd()
        result = _calc_trend_alignment_validation_v76(mmd, [1.0, 2.0])
        assert "数据不足" in result["msg"]

    def test_tav_ma_alignment_format(self):
        mmd = _make_mmd("3buy", 0.6)
        closes = [100.0 + i * 0.3 for i in range(100)]
        result = _calc_trend_alignment_validation_v76(mmd, closes)
        if result["ma_alignment"]:
            for ma in result["ma_alignment"]:
                assert "period" in ma
                assert "trend" in ma
                assert ma["trend"] in ("up", "down", "flat")

    # --- 条件238: 波动率自适应置信度 ---

    def test_vac_low_volatility(self):
        mmd = _make_mmd("3buy", 0.6)
        closes = [100.0 + 0.01 * i for i in range(100)]  # 低波动
        result = _calc_volatility_adaptive_confidence_v76(mmd, closes)
        assert result["vol_level"] in ("low", "normal", "high", "extreme", "unknown")
        assert result["atr_ratio"] >= 0
        assert 0.0 <= result["adaptive_confidence"] <= 1.0

    def test_vac_high_volatility(self):
        import random
        random.seed(99)
        mmd = _make_mmd("3buy", 0.6)
        closes = [100.0 + random.uniform(-10, 10) for _ in range(100)]
        result = _calc_volatility_adaptive_confidence_v76(mmd, closes)
        assert result["vol_level"] in ("low", "normal", "high", "extreme", "unknown")
        assert result["atr_ratio"] >= 0

    def test_vac_insufficient_data(self):
        mmd = _make_mmd()
        result = _calc_volatility_adaptive_confidence_v76(mmd, [1.0, 2.0])
        assert "数据不足" in result["msg"]

    # --- 条件239: 买卖点最终有效性 ---

    def test_sfv_no_adjustments(self):
        mmd = _make_mmd("3buy", 0.6)
        result = _calc_signal_final_validity_v76(mmd)
        assert result["final_validity"] in ("strong", "moderate", "weak", "invalid", "unknown")
        assert isinstance(result["validity_score"], float)
        assert 0.0 <= result["validity_score"] <= 1.0

    def test_sfv_with_adjustments(self):
        mmd = _make_mmd("3buy", 0.5)
        mmd._pullback_depth_validation_v75 = {"confidence_adjust": 0.05}
        mmd._price_structure_integrity_v76 = {"confidence_adjust": 0.03}
        result = _calc_signal_final_validity_v76(mmd)
        assert result["validity_score"] > 0.4

    def test_sfv_low_score(self):
        mmd = _make_mmd("3buy", 0.3)
        mmd._pullback_depth_validation_v75 = {"confidence_adjust": -0.06}
        result = _calc_signal_final_validity_v76(mmd)
        assert result["validity_score"] < 0.35

    # --- 综合冒烟测试 ---

    def test_all_v76_functions_no_crash(self):
        """所有 V76 函数在有数据时不应抛出异常"""
        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(100, 100.0)
        volumes = [1000.0] * 100

        r1 = _calc_price_structure_integrity_v76(mmd, closes, volumes)
        assert isinstance(r1, dict)

        r2 = _calc_trend_alignment_validation_v76(mmd, closes)
        assert isinstance(r2, dict)

        r3 = _calc_volatility_adaptive_confidence_v76(mmd, closes)
        assert isinstance(r3, dict)

        r4 = _calc_signal_final_validity_v76(mmd)
        assert isinstance(r4, dict)
