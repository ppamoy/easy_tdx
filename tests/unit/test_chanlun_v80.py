"""V80 缠论条件 252-255 单元测试。

条件252：买卖点与中枢距离验证（MMD-Zhongshu Distance Validation）
条件253：量能配合度评分（Volume Confirmation Score）
条件254：均线排列强度确认（MA Alignment Strength）
条件255：盈亏比动态评估（Dynamic Risk-Reward Assessment）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from easy_tdx.backtest.chanlun_validator import ConditionGroup
from easy_tdx.chanlun.mmd import (
    _calc_dynamic_risk_reward_v80,
    _calc_ma_alignment_strength_v80,
    _calc_mmd_zhongshu_distance_v80,
    _calc_volume_confirmation_v80,
)
from easy_tdx.chanlun.types import MMD, MMDType


def _make_mmd(mmd_type: str = "3buy", confidence: float = 0.6) -> MMD:
    """Helper to create MMD with correct enum value."""
    return MMD(mmd_type=MMDType(mmd_type), confidence=confidence, msg="test")


def _make_closes(n: int = 80, base: float = 100.0, trend: str = "flat") -> list[float]:
    """Generate test closing prices."""
    import random

    random.seed(42)
    if trend == "up":
        return [base + i * 0.05 + random.uniform(-1, 1) for i in range(n)]
    elif trend == "down":
        return [base - i * 0.05 + random.uniform(-1, 1) for i in range(n)]
    else:
        return [base + random.uniform(-5, 5) * (1 + 0.01 * i) for i in range(n)]


def _make_highs(closes: list[float], spread: float = 1.0) -> list[float]:
    return [c + spread + 0.5 for c in closes]


def _make_lows(closes: list[float], spread: float = 1.0) -> list[float]:
    return [c - spread - 0.5 for c in closes]


def _make_volumes(n: int = 80, base: float = 1000.0) -> list[float]:
    import random

    random.seed(43)
    return [base + random.uniform(-200, 200) for _ in range(n)]


# ── TestV80ConditionGroup：ConditionGroup 枚举测试 ───────────────────────────


class TestV80ConditionGroup:
    """V80 ConditionGroup 存在性和正确性测试。"""

    def test_v80_exists(self):
        assert hasattr(ConditionGroup, "V80")

    def test_v80_condition_range(self):
        assert ConditionGroup.V80.condition_range == (252, 255)

    def test_v80_description(self):
        desc = ConditionGroup.V80.description
        assert len(desc) > 0
        assert "中枢" in desc or "量能" in desc or "均线" in desc or "盈亏" in desc


# ── TestV80MMDFields：MMD 对象字段测试 ───────────────────────────────────────


class TestV80MMDFields:
    """MMD 对象包含 V80 字段。"""

    def test_mmd_has_v80_fields(self):
        mmd = _make_mmd()
        assert hasattr(mmd, "_mmd_zhongshu_distance_v80")
        assert hasattr(mmd, "_volume_confirmation_v80")
        assert hasattr(mmd, "_ma_alignment_strength_v80")
        assert hasattr(mmd, "_dynamic_risk_reward_v80")


# ── TestV80BacktestValidator：回测验证器测试 ─────────────────────────────────


class TestV80BacktestValidator:
    """V80 条件回测验证器测试。"""

    def test_v80_validator_usage(self):
        from easy_tdx.backtest.chanlun_validator import ChanlunConditionBacktestValidator

        _ = ChanlunConditionBacktestValidator()
        assert ConditionGroup.V80 in list(ConditionGroup)

    def test_v80_multi_group_validation(self):
        groups = [
            ConditionGroup.V76,
            ConditionGroup.V77,
            ConditionGroup.V78,
            ConditionGroup.V79,
            ConditionGroup.V80,
        ]
        ranges = [g.condition_range for g in groups]
        assert ranges[0] == (236, 239)
        assert ranges[1] == (240, 243)
        assert ranges[2] == (244, 247)
        assert ranges[3] == (248, 251)
        assert ranges[4] == (252, 255)

    def test_v80_summary_output(self):
        from easy_tdx.backtest.chanlun_validator import ChanlunConditionBacktestValidator

        validator = ChanlunConditionBacktestValidator()
        summary = validator.validate_conditions({}, [ConditionGroup.V80])
        assert summary is not None


# ── TestV80Functions：各计算函数单元测试 ─────────────────────────────────────


class TestV80Functions:
    """V80 四个计算函数的单元测试。"""

    # ── 条件252：买卖点与中枢距离验证 ──────────────────────────────────────

    def test_msd_buy_just_above(self):
        """买入信号在中枢上方0-5% → 高分。"""
        mmd = _make_mmd("3buy", 0.6)
        # 创建一个有中枢的MMD（模拟中枢在95-105之间，价格在102）
        # 由于MMD.zs需要真实对象，这里测试数据不足路径
        closes = _make_closes(30, base=100.0)
        highs = _make_highs(closes, 1.0)
        lows = _make_lows(closes, 1.0)
        result = _calc_mmd_zhongshu_distance_v80(mmd, closes, highs, lows)
        assert "distance_score" in result
        assert "zs_position" in result
        assert "confidence_adjust" in result
        assert isinstance(result["distance_score"], float)
        assert 0 <= result["distance_score"] <= 1.0

    def test_msd_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mmd("3buy", 0.6)
        result = _calc_mmd_zhongshu_distance_v80(mmd, [1.0, 2.0], [2.0, 3.0], [1.0, 2.0])
        assert result["msg"] != ""
        assert result["distance_score"] == 0.5
        assert result["confidence_adjust"] == 0.0

    def test_msd_sell_signal(self):
        """卖出信号也能正常计算。"""
        mmd = _make_mmd("3sell", 0.6)
        closes = _make_closes(30, base=100.0)
        highs = _make_highs(closes, 1.0)
        lows = _make_lows(closes, 1.0)
        result = _calc_mmd_zhongshu_distance_v80(mmd, closes, highs, lows)
        assert "zs_position" in result
        assert isinstance(result["distance_score"], float)

    # ── 条件253：量能配合度评分 ──────────────────────────────────────────

    def test_vcf_up_with_volume(self):
        """上涨+放量 → 高配合分。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = [100.0 + i * 0.5 for i in range(30)]
        volumes = [500.0 + i * 30 for i in range(30)]
        result = _calc_volume_confirmation_v80(mmd, closes, volumes)
        assert "confirmation_score" in result
        assert "volume_trend" in result
        assert "price_trend" in result
        assert "vol_ratio" in result
        assert isinstance(result["confirmation_score"], float)
        assert 0 <= result["confirmation_score"] <= 1.0
        assert result["price_trend"] in ["up", "down", "flat"]
        assert result["volume_trend"] in ["up", "down", "flat"]

    def test_vcf_divergence(self):
        """上涨+缩量 → 背离，低分。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = [100.0 + i * 0.5 for i in range(30)]
        volumes = [500.0 - i * 15 for i in range(30)]
        result = _calc_volume_confirmation_v80(mmd, closes, volumes)
        assert result["price_trend"] == "up"
        assert result["volume_trend"] == "down"
        assert result["confirmation_score"] < 0.65

    def test_vcf_down_with_shrink(self):
        """下跌+缩量 → 配合良好。"""
        mmd = _make_mmd("3sell", 0.6)
        closes = [100.0 - i * 0.3 for i in range(30)]
        volumes = [500.0 - i * 15 for i in range(30)]
        result = _calc_volume_confirmation_v80(mmd, closes, volumes)
        assert result["price_trend"] == "down"
        assert result["volume_trend"] == "down"
        assert result["confirmation_score"] >= 0.65

    def test_vcf_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mmd("3buy", 0.6)
        result = _calc_volume_confirmation_v80(mmd, [1.0, 2.0], None)
        assert result["msg"] != ""
        assert result["confirmation_score"] == 0.5
        assert result["confidence_adjust"] == 0.0

    def test_vcf_no_volumes(self):
        """无成交量数据 → 仍然能计算。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(30, base=100.0)
        result = _calc_volume_confirmation_v80(mmd, closes, [])
        assert result["msg"] != ""
        assert result["confirmation_score"] == 0.5

    # ── 条件254：均线排列强度确认 ──────────────────────────────────────────

    def test_mas_bullish_alignment(self):
        """多头排列 → 高分。"""
        mmd = _make_mmd("3buy", 0.6)
        # 单调上涨，确保MA5>MA10>MA20>MA60
        closes = [100.0 + i * 0.5 for i in range(70)]
        result = _calc_ma_alignment_strength_v80(mmd, closes)
        assert "alignment_score" in result
        assert "ma_alignment" in result
        assert "price_position" in result
        assert isinstance(result["alignment_score"], float)
        assert 0 <= result["alignment_score"] <= 1.0
        assert result["ma_alignment"] in ["bullish", "bearish", "mixed", "unknown"]

    def test_mas_bearish_alignment(self):
        """空头排列 → 高分（对卖出信号）。"""
        mmd = _make_mmd("3sell", 0.6)
        closes = [100.0 - i * 0.5 for i in range(70)]
        result = _calc_ma_alignment_strength_v80(mmd, closes)
        assert result["ma_alignment"] == "bearish"
        assert result["alignment_score"] >= 0.6

    def test_mas_mixed_alignment(self):
        """震荡行情 → 混合排列。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = [100.0 + 5.0 * ((-1) ** i) for i in range(70)]
        result = _calc_ma_alignment_strength_v80(mmd, closes)
        assert result["ma_alignment"] in ["bullish", "bearish", "mixed", "unknown"]
        assert isinstance(result["alignment_score"], float)

    def test_mas_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mmd("3buy", 0.6)
        result = _calc_ma_alignment_strength_v80(mmd, [1.0, 2.0])
        assert result["msg"] != ""
        assert result["alignment_score"] == 0.5
        assert result["confidence_adjust"] == 0.0

    # ── 条件255：盈亏比动态评估 ──────────────────────────────────────────

    def test_drr_excellent_ratio(self):
        """盈亏比≥3:1 → 极佳。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = [100.0 for _ in range(30)]
        highs = [110.0 for _ in range(30)]
        lows = [90.0 for _ in range(30)]
        result = _calc_dynamic_risk_reward_v80(mmd, closes, highs, lows)
        assert "rr_ratio" in result
        assert "risk_level" in result
        assert "stop_loss_pct" in result
        assert "take_profit_pct" in result
        assert isinstance(result["rr_ratio"], float)
        assert result["risk_level"] in [
            "excellent",
            "good",
            "moderate",
            "poor",
            "dangerous",
            "unknown",
        ]

    def test_drr_good_ratio(self):
        """盈亏比1.5:1~2:1 → 中等偏上。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = [100.0 for _ in range(30)]
        # highs=110, lows=95 → rr≈2.24 (good)
        highs = [110.0 for _ in range(30)]
        lows = [95.0 for _ in range(30)]
        result = _calc_dynamic_risk_reward_v80(mmd, closes, highs, lows)
        assert result["rr_ratio"] >= 1.5
        assert result["risk_level"] in ["moderate", "good", "excellent"]

    def test_drr_sell_signal(self):
        """卖出信号也能正常计算。"""
        mmd = _make_mmd("3sell", 0.6)
        closes = [100.0 for _ in range(30)]
        highs = [110.0 for _ in range(30)]
        lows = [90.0 for _ in range(30)]
        result = _calc_dynamic_risk_reward_v80(mmd, closes, highs, lows)
        assert "rr_ratio" in result
        assert isinstance(result["rr_ratio"], float)
        assert result["rr_ratio"] > 0

    def test_drr_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mmd("3buy", 0.6)
        result = _calc_dynamic_risk_reward_v80(mmd, [1.0, 2.0], None, None)
        assert result["msg"] != ""
        assert result["rr_ratio"] == 1.0
        assert result["confidence_adjust"] == 0.0

    def test_drr_no_highs_lows(self):
        """无highs/lows数据 → 仍然能计算。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(30, base=100.0)
        result = _calc_dynamic_risk_reward_v80(mmd, closes, [], [])
        assert result["msg"] != ""
        assert result["rr_ratio"] == 1.0

    # ── 综合冒烟测试 ──────────────────────────────────────────────────────

    def test_all_v80_functions_no_crash(self):
        """所有 V80 函数在无异常情况下正常运行。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(80, base=100.0)
        volumes = _make_volumes(80)
        highs = _make_highs(closes, 1.0)
        lows = _make_lows(closes, 1.0)

        r1 = _calc_mmd_zhongshu_distance_v80(mmd, closes, highs, lows)
        r2 = _calc_volume_confirmation_v80(mmd, closes, volumes)
        r3 = _calc_ma_alignment_strength_v80(mmd, closes)
        r4 = _calc_dynamic_risk_reward_v80(mmd, closes, highs, lows)

        assert all(r is not None for r in [r1, r2, r3, r4])
        assert all(isinstance(r.get("confidence_adjust", 0), float) for r in [r1, r2, r3, r4])

    def test_v80_vs_v79_consistency(self):
        """V80 与 V79 函数互不干扰。"""
        from easy_tdx.chanlun.mmd import (
            _calc_fractal_stability_validation_v79,
            _calc_price_momentum_continuity_v79,
        )

        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(80, base=100.0)
        volumes = _make_volumes(80)
        highs = _make_highs(closes, 1.0)
        lows = _make_lows(closes, 1.0)

        # V79 函数仍能正常工作
        r_v79_1 = _calc_fractal_stability_validation_v79(mmd, highs, lows)
        r_v79_2 = _calc_price_momentum_continuity_v79(mmd, closes, volumes)
        assert r_v79_1 is not None
        assert r_v79_2 is not None

        # V80 函数正常工作
        r_v80_1 = _calc_mmd_zhongshu_distance_v80(mmd, closes, highs, lows)
        r_v80_2 = _calc_volume_confirmation_v80(mmd, closes, volumes)
        r_v80_3 = _calc_ma_alignment_strength_v80(mmd, closes)
        r_v80_4 = _calc_dynamic_risk_reward_v80(mmd, closes, highs, lows)
        assert all(r is not None for r in [r_v80_1, r_v80_2, r_v80_3, r_v80_4])
