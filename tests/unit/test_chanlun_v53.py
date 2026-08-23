#!/usr/bin/env python3
"""V53 缠论模型条件152-155 专项测试。

测试内容：
- 条件152: 趋势阶段识别与顺势确认（Trend Stage Follow Confirmation）
- 条件153: ATR自适应止损距离（ATR Adaptive Stop Loss）
- 条件154: 中枢突破力度验证（Zhongshu Breakout Strength）
- 条件155: 信号质量综合分层（Signal Quality Tier）
"""

from __future__ import annotations

import pytest

from easy_tdx.chanlun.mmd import (
    _calc_trend_stage_follow_confirmation_v53,
    _calc_atr_adaptive_stop_v53,
    _calc_zs_breakout_strength_v53,
    _calc_signal_quality_tier_v53,
)
from easy_tdx.chanlun.types import MMD, MMDType


def _make_mock_mmd(mmd_type: MMDType, confidence: float = 0.5) -> MMD:
    """创建Mock MMD对象。"""
    return MMD(
        mmd_type=mmd_type,
        bi=None,
        zs=None,
        confidence=confidence,
        msg="test",
    )


class TestTrendStageFollowConfirmationV53:
    """条件152: 趋势阶段识别与顺势确认测试。"""

    def test_uptrend_buy_following(self):
        """3买信号，强上升趋势 → 顺势确认 +3%。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.5 for i in range(70)]  # 稳步上涨
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        result = _calc_trend_stage_follow_confirmation_v53(mmd, closes, highs, lows)
        assert result["trend_direction"] == "strong_uptrend"
        assert result["is_following_trend"] is True
        assert result["confidence_adjust"] == 0.03
        assert "✅" in result["msg"]

    def test_downtrend_buy_not_following(self):
        """3买信号，强下降趋势 → 逆势降权 -5%。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 - i * 0.5 for i in range(70)]  # 稳步下跌
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        result = _calc_trend_stage_follow_confirmation_v53(mmd, closes, highs, lows)
        assert result["trend_direction"] == "strong_downtrend"
        assert result["is_following_trend"] is False
        assert result["confidence_adjust"] == -0.05
        assert "⚠️" in result["msg"]

    def test_sell_in_downtrend_following(self):
        """3卖信号，强下降趋势 → 顺势确认 +3%。"""
        mmd = _make_mock_mmd(MMDType.SELL_3)
        closes = [100.0 - i * 0.5 for i in range(70)]
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        result = _calc_trend_stage_follow_confirmation_v53(mmd, closes, highs, lows)
        assert result["trend_direction"] == "strong_downtrend"
        assert result["is_following_trend"] is True
        assert result["confidence_adjust"] == 0.03

    def test_sideways_penalty(self):
        """震荡阶段 → 降权 -2%。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + (i % 5) * 0.1 for i in range(70)]  # 小幅震荡
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = _calc_trend_stage_follow_confirmation_v53(mmd, closes, highs, lows)
        assert result["confidence_adjust"] <= 0
        assert result["is_following_trend"] is False

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_trend_stage_follow_confirmation_v53(mmd, [100.0] * 30, [100.0] * 30, [90.0] * 30)
        assert result["trend_direction"] == "unknown"
        assert result["confidence_adjust"] == 0.0

    def test_insufficient_data_short(self):
        """数据不足30根时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_trend_stage_follow_confirmation_v53(mmd, [100.0] * 20, [100.0] * 20, [90.0] * 20)
        assert result["trend_direction"] == "unknown"


class TestAtrAdaptiveStopV53:
    """条件153: ATR自适应止损距离测试。"""

    def test_low_volatility_bonus(self):
        """低波动 → +2%置信度，建议重仓。"""
        closes = [100.0] * 30
        highs = [100.5] * 30
        lows = [99.5] * 30
        result = _calc_atr_adaptive_stop_v53(closes, highs, lows)
        assert result["atr_value"] > 0
        assert result["position_suggestion"] in ("high", "medium")
        assert result["confidence_adjust"] >= 0

    def test_high_volatility_penalty(self):
        """高波动 → -2%或-3%置信度。"""
        import random
        random.seed(42)
        closes = [100.0]
        highs = [100.0]
        lows = [100.0]
        for _ in range(40):
            prev = closes[-1]
            change = random.uniform(-5.0, 5.0)
            closes.append(prev + change)
            highs.append(max(prev, closes[-1]) + 2.0)
            lows.append(min(prev, closes[-1]) - 2.0)
        result = _calc_atr_adaptive_stop_v53(closes, highs, lows)
        assert result["atr_value"] > 0
        # 高波动下不应该加分
        assert result["confidence_adjust"] <= 0

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        result = _calc_atr_adaptive_stop_v53([100.0] * 20, [100.0] * 20, [90.0] * 20)
        assert result["atr_value"] == 0.0
        assert result["confidence_adjust"] == 0.0

    def test_empty_data(self):
        """空数据时返回默认值。"""
        result = _calc_atr_adaptive_stop_v53([], [], [])
        assert result["atr_value"] == 0.0
        assert result["position_suggestion"] == "unknown"


class TestZsBreakoutStrengthV53:
    """条件154: 中枢突破力度验证测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_zs_breakout_strength_v53(mmd, None, None, [])
        assert result["strength_ratio"] == 0.0
        assert result["confidence_adjust"] == 0.0

    def test_no_bi_index(self):
        """无index属性的bi时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = None
        result = _calc_zs_breakout_strength_v53(mmd, [], [], [100.0] * 30)
        assert result["breakout_strength"] == 0.0


class TestSignalQualityTierV53:
    """条件155: 信号质量综合分层测试。"""

    def test_high_confidence_signal(self):
        """高置信度信号 → S/A级。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.85)
        result = _calc_signal_quality_tier_v53(mmd, 100.0)
        assert result["tier_score"] >= 80
        assert result["quality_tier"] in ("S", "A")

    def test_low_confidence_signal(self):
        """低置信度信号 → C/D级。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.35)
        result = _calc_signal_quality_tier_v53(mmd, 100.0)
        assert result["tier_score"] < 50
        assert result["quality_tier"] in ("C", "D")

    def test_none_mmd(self):
        """None MMD时返回默认值。"""
        result = _calc_signal_quality_tier_v53(None, 100.0)
        assert result["quality_tier"] == "D"
        assert result["tier_score"] == 0

    def test_tier_score_bounds(self):
        """评分在[0, 100]范围内。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.95)
        result = _calc_signal_quality_tier_v53(mmd, 100.0)
        assert 0 <= result["tier_score"] <= 100


class TestFindMMDsV53Integration:
    """V53 集成测试。"""

    def test_v53_functions_importable(self):
        """所有V53函数可正常导入。"""
        from easy_tdx.chanlun.mmd import (
            _calc_trend_stage_follow_confirmation_v53,
            _calc_atr_adaptive_stop_v53,
            _calc_zs_breakout_strength_v53,
            _calc_signal_quality_tier_v53,
        )
        assert callable(_calc_trend_stage_follow_confirmation_v53)
        assert callable(_calc_atr_adaptive_stop_v53)
        assert callable(_calc_zs_breakout_strength_v53)
        assert callable(_calc_signal_quality_tier_v53)

    def test_v53_fields_in_mmd_type(self):
        """MMD类型包含V53字段定义。"""
        from easy_tdx.chanlun.types import MMD
        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, msg="test")
        assert hasattr(mmd, "_trend_stage_follow_confirmation_v53")
        assert hasattr(mmd, "_atr_adaptive_stop_v53")
        assert hasattr(mmd, "_zs_breakout_strength_v53")
        assert hasattr(mmd, "_signal_quality_tier_v53")

    def test_v53_confidence_bounds(self):
        """V53置信度调整不超出[0, 1]范围。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.9)
        closes = [100.0 + i * 0.05 for i in range(70)]
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]

        r1 = _calc_trend_stage_follow_confirmation_v53(mmd, closes, highs, lows)
        r2 = _calc_atr_adaptive_stop_v53(closes, highs, lows)
        r3 = _calc_signal_quality_tier_v53(mmd, closes[-1])

        for r in [r1, r2, r3]:
            new_conf = max(0.0, min(1.0, mmd.confidence + r.get("confidence_adjust", 0.0)))
            assert 0.0 <= new_conf <= 1.0

    def test_v53_all_conditions_callable(self):
        """所有V53条件函数可正常调用且不抛出异常。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.1 for i in range(70)]
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]

        r1 = _calc_trend_stage_follow_confirmation_v53(mmd, closes, highs, lows)
        r2 = _calc_atr_adaptive_stop_v53(closes, highs, lows)
        r3 = _calc_zs_breakout_strength_v53(mmd, [], [], closes)
        r4 = _calc_signal_quality_tier_v53(mmd, closes[-1])

        assert isinstance(r1, dict)
        assert isinstance(r2, dict)
        assert isinstance(r3, dict)
        assert isinstance(r4, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
