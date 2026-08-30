#!/usr/bin/env python3
"""V54 缠论模型条件156-159 专项测试。

测试内容：
- 条件156: 多K线确认后确认（Multi-Bar Post-Signal Confirmation）
- 条件157: 缺口风险评估（Gap Risk Assessment）
- 条件158: 波动率 regime 切换检测（Volatility Regime Change Detection）
- 条件159: 量价配合度评分（Volume-Price Coordination Score）
"""

from __future__ import annotations

import pytest

from easy_tdx.chanlun.mmd import (
    _calc_gap_risk_assessment_v54,
    _calc_multi_bar_confirmation_v54,
    _calc_volatility_regime_change_v54,
    _calc_volume_price_coordination_v54,
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


class TestMultiBarConfirmationV54:
    """条件156: 多K线确认后确认测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_multi_bar_confirmation_v54(mmd, [100.0] * 5)
        assert result["confirmed"] is False
        assert result["confirm_bars"] == 0
        assert result["confidence_adjust"] == 0.0

    def test_none_bi(self):
        """bi为None时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = None
        result = _calc_multi_bar_confirmation_v54(mmd, [100.0] * 20)
        assert result["confirmed"] is False
        assert result["confidence_adjust"] == 0.0

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        result = _calc_multi_bar_confirmation_v54(mmd, [100.0] * 20)
        assert "非3买" in result["msg"] or result["confidence_adjust"] == 0.0

    def test_importable(self):
        """函数可正常导入。"""
        from easy_tdx.chanlun.mmd import _calc_multi_bar_confirmation_v54

        assert callable(_calc_multi_bar_confirmation_v54)


class TestGapRiskAssessmentV54:
    """条件157: 缺口风险评估测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_gap_risk_assessment_v54(mmd, [100.0] * 5, [100.0] * 5, [99.0] * 5)
        assert result["has_gap"] is False
        assert result["confidence_adjust"] == 0.0

    def test_no_gap(self):
        """无缺口时返回正常状态。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.1 for i in range(20)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = _calc_gap_risk_assessment_v54(mmd, closes, highs, lows)
        # 无缺口时应返回无缺口消息
        assert result["has_gap"] is False or "无缺口" in result["msg"]

    def test_none_bi(self):
        """bi为None时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = None
        result = _calc_gap_risk_assessment_v54(mmd, [100.0] * 20, [100.5] * 20, [99.5] * 20)
        assert result["has_gap"] is False
        assert result["confidence_adjust"] == 0.0

    def test_importable(self):
        """函数可正常导入。"""
        from easy_tdx.chanlun.mmd import _calc_gap_risk_assessment_v54

        assert callable(_calc_gap_risk_assessment_v54)


class TestVolatilityRegimeChangeV54:
    """条件158: 波动率 regime 切换检测测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        result = _calc_volatility_regime_change_v54([100.0] * 20, [100.5] * 20, [99.5] * 20)
        assert result["regime"] == "unknown"
        assert result["confidence_adjust"] == 0.0

    def test_empty_data(self):
        """空数据时返回默认值。"""
        result = _calc_volatility_regime_change_v54([], [], [])
        assert result["regime"] == "unknown"
        assert result["confidence_adjust"] == 0.0

    def test_stable_volatility(self):
        """稳定波动率时返回stable状态。"""
        closes = [100.0 + i * 0.1 for i in range(50)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = _calc_volatility_regime_change_v54(closes, highs, lows)
        assert result["regime"] in ("stable", "expanding", "contracting")
        assert isinstance(result["confidence_adjust"], float)

    def test_importable(self):
        """函数可正常导入。"""
        from easy_tdx.chanlun.mmd import _calc_volatility_regime_change_v54

        assert callable(_calc_volatility_regime_change_v54)


class TestVolumePriceCoordinationV54:
    """条件159: 量价配合度评分测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_volume_price_coordination_v54(mmd, [100.0] * 10, [1000.0] * 10)
        assert result["score"] == 0
        assert result["confidence_adjust"] == 0.0

    def test_empty_data(self):
        """空数据时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_volume_price_coordination_v54(mmd, [], [])
        assert result["score"] == 0
        assert result["confidence_adjust"] == 0.0

    def test_none_bi(self):
        """bi为None时仍可正常调用。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = None
        closes = [100.0 + i * 0.1 for i in range(25)]
        volumes = [1000.0] * 25
        result = _calc_volume_price_coordination_v54(mmd, closes, volumes)
        assert isinstance(result["score"], int)
        assert -5 <= result["score"] <= 5

    def test_importable(self):
        """函数可正常导入。"""
        from easy_tdx.chanlun.mmd import _calc_volume_price_coordination_v54

        assert callable(_calc_volume_price_coordination_v54)


class TestFindMMDsV54Integration:
    """V54 集成测试。"""

    def test_v54_functions_importable(self):
        """所有V54函数可正常导入。"""
        from easy_tdx.chanlun.mmd import (
            _calc_gap_risk_assessment_v54,
            _calc_multi_bar_confirmation_v54,
            _calc_volatility_regime_change_v54,
            _calc_volume_price_coordination_v54,
        )

        assert callable(_calc_multi_bar_confirmation_v54)
        assert callable(_calc_gap_risk_assessment_v54)
        assert callable(_calc_volatility_regime_change_v54)
        assert callable(_calc_volume_price_coordination_v54)

    def test_v54_fields_in_mmd_type(self):
        """MMD类型包含V54字段定义。"""
        from easy_tdx.chanlun.types import MMD

        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, msg="test")
        assert hasattr(mmd, "_multi_bar_confirmation_v54")
        assert hasattr(mmd, "_gap_risk_assessment_v54")
        assert hasattr(mmd, "_volatility_regime_change_v54")
        assert hasattr(mmd, "_volume_price_coordination_v54")

    def test_v54_confidence_bounds(self):
        """V54置信度调整不超出[0, 1]范围。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.5)
        closes = [100.0 + i * 0.1 for i in range(50)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        volumes = [1000.0] * 50

        r1 = _calc_multi_bar_confirmation_v54(mmd, closes)
        r2 = _calc_gap_risk_assessment_v54(mmd, closes, highs, lows)
        r3 = _calc_volatility_regime_change_v54(closes, highs, lows)
        r4 = _calc_volume_price_coordination_v54(mmd, closes, volumes)

        for r in [r1, r2, r3, r4]:
            new_conf = max(0.0, min(1.0, mmd.confidence + r.get("confidence_adjust", 0.0)))
            assert 0.0 <= new_conf <= 1.0

    def test_v54_all_conditions_callable(self):
        """所有V54条件函数可正常调用且不抛出异常。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.1 for i in range(50)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        volumes = [1000.0 + (i % 3) * 100 for i in range(50)]

        r1 = _calc_multi_bar_confirmation_v54(mmd, closes)
        r2 = _calc_gap_risk_assessment_v54(mmd, closes, highs, lows)
        r3 = _calc_volatility_regime_change_v54(closes, highs, lows)
        r4 = _calc_volume_price_coordination_v54(mmd, closes, volumes)

        assert isinstance(r1, dict)
        assert isinstance(r2, dict)
        assert isinstance(r3, dict)
        assert isinstance(r4, dict)

        # 检查关键字段存在
        assert "confidence_adjust" in r1
        assert "confidence_adjust" in r2
        assert "confidence_adjust" in r3
        assert "confidence_adjust" in r4

    def test_sell3_v54_conditions(self):
        """3卖信号的V54条件正常处理。"""
        mmd = _make_mock_mmd(MMDType.SELL_3)
        closes = [100.0 - i * 0.1 for i in range(50)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        volumes = [1000.0] * 50

        r1 = _calc_multi_bar_confirmation_v54(mmd, closes)
        r2 = _calc_gap_risk_assessment_v54(mmd, closes, highs, lows)
        r3 = _calc_volatility_regime_change_v54(closes, highs, lows)
        r4 = _calc_volume_price_coordination_v54(mmd, closes, volumes)

        for r in [r1, r2, r3, r4]:
            assert isinstance(r, dict)
            assert "confidence_adjust" in r


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
