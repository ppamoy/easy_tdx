#!/usr/bin/env python3
"""V58 缠论模型条件172-175 专项测试。

测试内容：
- 条件172: 多时间框架趋势一致性验证（Multi-Timeframe Trend Consistency）
- 条件173: 成交量堆积验证（Volume Accumulation Validation）
- 条件174: ATR自适应止损距离（ATR Adaptive Stop Distance）
- 条件175: 信号质量综合评分（Composite Quality Score）
"""

from __future__ import annotations

from easy_tdx.chanlun.mmd import (
    _calc_atr_adaptive_stop_v58,
    _calc_composite_quality_score_v58,
    _calc_multi_tf_trend_consistency_v58,
    _calc_volume_accumulation_validation_v58,
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


class TestMultiTFTrendConsistencyV58:
    """条件172: 多时间框架趋势一致性测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_multi_tf_trend_consistency_v58(mmd, [100.0] * 10)
        assert "数据不足" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        closes = [100.0 + i * 0.1 for i in range(70)]
        result = _calc_multi_tf_trend_consistency_v58(mmd, closes)
        assert "非3买/3卖信号" in result["msg"]

    def test_bullish_alignment(self):
        """多头排列时+3%置信度。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 递增数列 → 多头排列
        closes = [100.0 + i * 0.5 for i in range(70)]
        result = _calc_multi_tf_trend_consistency_v58(mmd, closes)
        assert result["bullish_alignment"] is True
        assert result["confidence_adjust"] == 0.03
        assert "+3%置信度" in result["msg"]

    def test_bearish_alignment(self):
        """空头排列时-3%置信度。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 递减数列 → 空头排列
        closes = [100.0 - i * 0.5 for i in range(70)]
        result = _calc_multi_tf_trend_consistency_v58(mmd, closes)
        assert result["bearish_alignment"] is True
        assert result["confidence_adjust"] == -0.03

    def test_sell3_bearish_enhance(self):
        """3卖信号：空头排列增强(+3%)。"""
        mmd = _make_mock_mmd(MMDType.SELL_3)
        closes = [100.0 - i * 0.5 for i in range(70)]
        result = _calc_multi_tf_trend_consistency_v58(mmd, closes)
        assert result["confidence_adjust"] == 0.03

    def test_interleaved_ma(self):
        """均线交错时0%调整。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 震荡数列
        closes = [100.0] * 70
        result = _calc_multi_tf_trend_consistency_v58(mmd, closes)
        assert result["confidence_adjust"] == 0.0


class TestVolumeAccumulationValidationV58:
    """条件173: 成交量堆积验证测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_volume_accumulation_validation_v58(mmd, [100.0] * 10, [1000.0] * 10)
        assert "数据不足" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        closes = [100.0 + i * 0.1 for i in range(30)]
        volumes = [1000.0] * 30
        result = _calc_volume_accumulation_validation_v58(mmd, closes, volumes)
        assert "非3买/3卖信号" in result["msg"]

    def test_high_volume_ratio(self):
        """放量突破(量比≥1.5)时+3%置信度。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.1 for i in range(30)]
        # 近5根量是近20根平均的2倍
        volumes = [1000.0] * 25 + [2000.0] * 5
        result = _calc_volume_accumulation_validation_v58(mmd, closes, volumes)
        assert result["volume_adequate"] is True
        assert result["confidence_adjust"] == 0.03

    def test_mild_volume_ratio(self):
        """温和放量(量比1.0-1.5)时+1%置信度。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.1 for i in range(30)]
        volumes = [1000.0] * 25 + [1200.0] * 5
        result = _calc_volume_accumulation_validation_v58(mmd, closes, volumes)
        assert result["volume_adequate"] is True
        assert result["confidence_adjust"] == 0.01

    def test_low_volume_ratio(self):
        """缩量突破(量比<1.0)时-3%置信度。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.1 for i in range(30)]
        volumes = [1000.0] * 25 + [500.0] * 5
        result = _calc_volume_accumulation_validation_v58(mmd, closes, volumes)
        assert result["volume_adequate"] is False
        assert result["confidence_adjust"] == -0.03

    def test_returns_dict_structure(self):
        """返回结构包含必要字段。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.1 for i in range(30)]
        volumes = [1000.0] * 30
        result = _calc_volume_accumulation_validation_v58(mmd, closes, volumes)
        assert "volume_ratio" in result
        assert "recent_vol" in result
        assert "avg_vol_20" in result
        assert "volume_adequate" in result
        assert "confidence_adjust" in result
        assert "msg" in result


class TestATRAdaptiveStopV58:
    """条件174: ATR自适应止损距离测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        highs = [100.0] * 10
        lows = [99.0] * 10
        result = _calc_atr_adaptive_stop_v58(mmd, highs, lows)
        assert "数据不足" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        highs = [100.0 + i * 0.1 for i in range(20)]
        lows = [99.0 + i * 0.1 for i in range(20)]
        result = _calc_atr_adaptive_stop_v58(mmd, highs, lows)
        assert "非3买/3卖信号" in result["msg"]

    def test_low_volatility(self):
        """低波动率时正确计算止损位。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 低波动：价差0.1
        highs = [100.05 + i * 0.1 for i in range(20)]
        lows = [99.95 + i * 0.1 for i in range(20)]
        result = _calc_atr_adaptive_stop_v58(mmd, highs, lows)
        assert result["atr_14"] > 0
        assert result["stop_loss_price"] > 0
        assert result["volatility_level"] == "low"
        assert result["confidence_adjust"] == 0.0

    def test_high_volatility(self):
        """高波动率时-1%置信度。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 高波动：价差5元，价格100
        highs = [102.5 + i * 0.5 for i in range(20)]
        lows = [97.5 + i * 0.5 for i in range(20)]
        result = _calc_atr_adaptive_stop_v58(mmd, highs, lows)
        assert result["volatility_level"] in ("high", "extreme")
        assert result["confidence_adjust"] < 0

    def test_sell3_direction(self):
        """3卖信号时止损位在上方。"""
        mmd = _make_mock_mmd(MMDType.SELL_3)
        highs = [100.05 + i * 0.1 for i in range(20)]
        lows = [99.95 + i * 0.1 for i in range(20)]
        result = _calc_atr_adaptive_stop_v58(mmd, highs, lows)
        assert result["stop_loss_price"] > highs[-1]

    def test_returns_dict_structure(self):
        """返回结构包含必要字段。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        highs = [100.05 + i * 0.1 for i in range(20)]
        lows = [99.95 + i * 0.1 for i in range(20)]
        result = _calc_atr_adaptive_stop_v58(mmd, highs, lows)
        assert "atr_14" in result
        assert "stop_loss_price" in result
        assert "volatility_level" in result
        assert "confidence_adjust" in result
        assert "msg" in result


class TestCompositeQualityScoreV58:
    """条件175: 信号质量综合评分测试。"""

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        result = _calc_composite_quality_score_v58(mmd)
        assert "非3买/3卖信号" in result["msg"]

    def test_all_none_scores(self):
        """所有条件均为None时返回B级（总调整=0%属于B档）。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_composite_quality_score_v58(mmd)
        assert result["grade"] == "B"
        assert result["total_adjust"] == 0.0

    def test_positive_total_grade_a(self):
        """正向总调整≥+5%时评A级。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd._pullback_filter_v57 = {"confidence_adjust": 0.03, "msg": "ok"}
        mmd._breakout_strength_validation_v57 = {"confidence_adjust": 0.03, "msg": "ok"}
        result = _calc_composite_quality_score_v58(mmd)
        assert result["grade"] == "A"
        assert result["total_adjust"] == 0.06

    def test_negative_total_grade_d(self):
        """负向总调整<-5%时评D级。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd._pullback_filter_v57 = {"confidence_adjust": -0.05, "msg": "ok"}
        mmd._zs_divergence_check_v57 = {"confidence_adjust": -0.03, "msg": "ok"}
        result = _calc_composite_quality_score_v58(mmd)
        assert result["grade"] == "D"
        assert result["total_adjust"] == -0.08

    def test_detail_scores_tracked(self):
        """detail_scores正确记录各条件调整值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd._pullback_filter_v57 = {"confidence_adjust": 0.03, "msg": "ok"}
        result = _calc_composite_quality_score_v58(mmd)
        assert "pullback_filter_v57" in result["detail_scores"]
        assert result["detail_scores"]["pullback_filter_v57"] == 0.03

    def test_returns_dict_structure(self):
        """返回结构包含必要字段。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_composite_quality_score_v58(mmd)
        assert "total_adjust" in result
        assert "grade" in result
        assert "grade_desc" in result
        assert "detail_scores" in result
        assert "msg" in result


class TestFindMMDsV58Integration:
    """V58 集成测试。"""

    def test_v58_functions_importable(self):
        """所有V58函数可导入。"""
        from easy_tdx.chanlun.mmd import (
            _calc_atr_adaptive_stop_v58,
            _calc_composite_quality_score_v58,
            _calc_multi_tf_trend_consistency_v58,
            _calc_volume_accumulation_validation_v58,
        )

        assert callable(_calc_multi_tf_trend_consistency_v58)
        assert callable(_calc_volume_accumulation_validation_v58)
        assert callable(_calc_atr_adaptive_stop_v58)
        assert callable(_calc_composite_quality_score_v58)

    def test_v58_fields_in_mmd_type(self):
        """MMD类型包含V58字段。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        assert hasattr(mmd, "_multi_tf_trend_consistency_v58")
        assert hasattr(mmd, "_volume_accumulation_validation_v58")
        assert hasattr(mmd, "_atr_adaptive_stop_v58")
        assert hasattr(mmd, "_composite_quality_score_v58")

    def test_v58_confidence_bounds(self):
        """置信度在合理范围内。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.5)
        closes = [100.0 + i * 0.5 for i in range(70)]
        result = _calc_multi_tf_trend_consistency_v58(mmd, closes)
        assert -1.0 <= result["confidence_adjust"] <= 1.0

    def test_v58_all_conditions_callable(self):
        """所有V58条件均可正常调用不抛异常。"""
        mmd_buy = _make_mock_mmd(MMDType.BUY_3)
        mmd_sell = _make_mock_mmd(MMDType.SELL_3)
        closes = [100.0 + i * 0.1 for i in range(70)]
        volumes = [1000.0] * 70
        highs = [100.05 + i * 0.1 for i in range(20)]
        lows = [99.95 + i * 0.1 for i in range(20)]

        r1 = _calc_multi_tf_trend_consistency_v58(mmd_buy, closes)
        r2 = _calc_volume_accumulation_validation_v58(mmd_buy, closes, volumes)
        r3 = _calc_atr_adaptive_stop_v58(mmd_sell, highs, lows)
        r4 = _calc_composite_quality_score_v58(mmd_buy)

        assert all(isinstance(r, dict) for r in [r1, r2, r3, r4])

    def test_sell3_v58_conditions(self):
        """3卖信号的V58条件行为正确。"""
        mmd = _make_mock_mmd(MMDType.SELL_3)
        # 多头排列应弱化3卖信号
        closes = [100.0 + i * 0.5 for i in range(70)]
        result = _calc_multi_tf_trend_consistency_v58(mmd, closes)
        assert result["confidence_adjust"] == -0.03
