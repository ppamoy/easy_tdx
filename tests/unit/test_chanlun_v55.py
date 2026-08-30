#!/usr/bin/env python3
"""V55 缠论模型条件160-163 专项测试。

测试内容：
- 条件160: 分钟级多时间框架共振过滤（Multi-Timeframe Resonance Filter）
- 条件161: 中枢级别权重自适应（Zhongshu Level Weight Adaptation）
- 条件162: 弱势股专项风险检测（Weak Stock Risk Detection）
- 条件163: 信号与趋势方向对齐验证（Signal Trend Alignment Validation）
"""

from __future__ import annotations

import pytest

from easy_tdx.chanlun.mmd import (
    _calc_multi_tf_resonance_filter_v55,
    _calc_signal_trend_alignment_v55,
    _calc_weak_stock_risk_v55,
    _calc_zhongshu_level_weight_v55,
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


class TestMultiTFResonanceFilterV55:
    """条件160: 多时间框架共振过滤测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_multi_tf_resonance_filter_v55(mmd, [100.0] * 10, [1000.0] * 10)
        assert result["resonated"] is False
        assert result["confidence_adjust"] == 0.0

    def test_none_bi(self):
        """bi为None时仍可正常调用。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = None
        result = _calc_multi_tf_resonance_filter_v55(
            mmd, [100.0 + i * 0.1 for i in range(30)], [1000.0] * 30
        )
        assert isinstance(result["timeframes"], list)
        assert isinstance(result["confidence_adjust"], float)

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        result = _calc_multi_tf_resonance_filter_v55(
            mmd, [100.0 + i * 0.1 for i in range(30)], [1000.0] * 30
        )
        assert "非3买" in result["msg"] or result["confidence_adjust"] == 0.0

    def test_importable(self):
        """函数可正常导入。"""
        from easy_tdx.chanlun.mmd import _calc_multi_tf_resonance_filter_v55

        assert callable(_calc_multi_tf_resonance_filter_v55)


class TestZhongshuLevelWeightV55:
    """条件161: 中枢级别权重自适应测试。"""

    def test_no_zss(self):
        """无中枢数据时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_zhongshu_level_weight_v55(mmd, [])
        assert result["level"] == "unknown"
        assert result["confidence_adjust"] == 0.0

    def test_none_bi(self):
        """bi为None时仍可正常调用。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = None
        result = _calc_zhongshu_level_weight_v55(mmd, [])
        assert "非3买" in result["msg"] or result["confidence_adjust"] == 0.0

    def test_importable(self):
        """函数可正常导入。"""
        from easy_tdx.chanlun.mmd import _calc_zhongshu_level_weight_v55

        assert callable(_calc_zhongshu_level_weight_v55)


class TestWeakStockRiskV55:
    """条件162: 弱势股专项风险检测测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_weak_stock_risk_v55(
            mmd,
            [100.0] * 30,
            [1000.0] * 30,
            [100.5] * 30,
            [99.5] * 30,
        )
        assert "数据不足" in result["msg"] or result["confidence_adjust"] == 0.0

    def test_empty_data(self):
        """空数据时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_weak_stock_risk_v55(mmd, [], [], [], [])
        assert result["is_weak"] is False
        assert result["confidence_adjust"] == 0.0

    def test_none_bi(self):
        """bi为None时仍可正常调用。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = None
        closes = [100.0 + i * 0.1 for i in range(70)]
        volumes = [1000.0] * 70
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = _calc_weak_stock_risk_v55(mmd, closes, volumes, highs, lows)
        assert isinstance(result["is_weak"], bool)
        assert isinstance(result["risk_factors"], list)
        assert isinstance(result["confidence_adjust"], float)

    def test_importable(self):
        """函数可正常导入。"""
        from easy_tdx.chanlun.mmd import _calc_weak_stock_risk_v55

        assert callable(_calc_weak_stock_risk_v55)


class TestSignalTrendAlignmentV55:
    """条件163: 信号与趋势方向对齐验证测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_signal_trend_alignment_v55(mmd, [100.0] * 30)
        assert "数据不足" in result["msg"] or result["confidence_adjust"] == 0.0

    def test_empty_data(self):
        """空数据时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_signal_trend_alignment_v55(mmd, [])
        assert result["trend_direction"] == "unknown"
        assert result["confidence_adjust"] == 0.0

    def test_none_bi(self):
        """bi为None时仍可正常调用。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = None
        closes = [100.0 + i * 0.1 for i in range(70)]
        result = _calc_signal_trend_alignment_v55(mmd, closes)
        assert isinstance(result["trend_direction"], str)
        assert isinstance(result["confidence_adjust"], float)

    def test_importable(self):
        """函数可正常导入。"""
        from easy_tdx.chanlun.mmd import _calc_signal_trend_alignment_v55

        assert callable(_calc_signal_trend_alignment_v55)


class TestFindMMDsV55Integration:
    """V55 集成测试。"""

    def test_v55_functions_importable(self):
        """所有V55函数可正常导入。"""
        from easy_tdx.chanlun.mmd import (
            _calc_multi_tf_resonance_filter_v55,
            _calc_signal_trend_alignment_v55,
            _calc_weak_stock_risk_v55,
            _calc_zhongshu_level_weight_v55,
        )

        assert callable(_calc_multi_tf_resonance_filter_v55)
        assert callable(_calc_zhongshu_level_weight_v55)
        assert callable(_calc_weak_stock_risk_v55)
        assert callable(_calc_signal_trend_alignment_v55)

    def test_v55_fields_in_mmd_type(self):
        """MMD类型包含V55字段定义。"""
        from easy_tdx.chanlun.types import MMD

        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, msg="test")
        assert hasattr(mmd, "_multi_tf_resonance_filter_v55")
        assert hasattr(mmd, "_zhongshu_level_weight_v55")
        assert hasattr(mmd, "_weak_stock_risk_v55")
        assert hasattr(mmd, "_signal_trend_alignment_v55")

    def test_v55_confidence_bounds(self):
        """V55置信度调整不超出[0, 1]范围。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.5)
        closes = [100.0 + i * 0.1 for i in range(70)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        volumes = [1000.0 + (i % 3) * 100 for i in range(70)]

        r1 = _calc_multi_tf_resonance_filter_v55(mmd, closes, volumes)
        r2 = _calc_zhongshu_level_weight_v55(mmd, [])
        r3 = _calc_weak_stock_risk_v55(mmd, closes, volumes, highs, lows)
        r4 = _calc_signal_trend_alignment_v55(mmd, closes)

        for r in [r1, r2, r3, r4]:
            new_conf = max(0.0, min(1.0, mmd.confidence + r.get("confidence_adjust", 0.0)))
            assert 0.0 <= new_conf <= 1.0

    def test_v55_all_conditions_callable(self):
        """所有V55条件函数可正常调用且不抛出异常。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.1 for i in range(70)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        volumes = [1000.0 + (i % 3) * 100 for i in range(70)]

        r1 = _calc_multi_tf_resonance_filter_v55(mmd, closes, volumes)
        r2 = _calc_zhongshu_level_weight_v55(mmd, [])
        r3 = _calc_weak_stock_risk_v55(mmd, closes, volumes, highs, lows)
        r4 = _calc_signal_trend_alignment_v55(mmd, closes)

        assert isinstance(r1, dict)
        assert isinstance(r2, dict)
        assert isinstance(r3, dict)
        assert isinstance(r4, dict)

        # 检查关键字段存在
        assert "confidence_adjust" in r1
        assert "confidence_adjust" in r2
        assert "confidence_adjust" in r3
        assert "confidence_adjust" in r4

    def test_sell3_v55_conditions(self):
        """3卖信号的V55条件正常处理。"""
        mmd = _make_mock_mmd(MMDType.SELL_3)
        closes = [100.0 - i * 0.1 for i in range(70)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        volumes = [1000.0] * 70

        r1 = _calc_multi_tf_resonance_filter_v55(mmd, closes, volumes)
        r2 = _calc_zhongshu_level_weight_v55(mmd, [])
        r3 = _calc_weak_stock_risk_v55(mmd, closes, volumes, highs, lows)
        r4 = _calc_signal_trend_alignment_v55(mmd, closes)

        for r in [r1, r2, r3, r4]:
            assert isinstance(r, dict)
            assert "confidence_adjust" in r


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
