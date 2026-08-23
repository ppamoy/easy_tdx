#!/usr/bin/env python3
"""V50 缠论模型条件140-143 专项测试。

测试内容：
- 条件140：板块联动分析（Sector Correlation Analysis）
- 条件141：多时间框架共振验证（Multi-Timeframe Resonance）
- 条件142：缠论级别递归验证（Multi-Level Chanlun Recursive Validation）
- 条件143：市场情绪指标融合（Market Sentiment Fusion）
"""

from __future__ import annotations

import pytest

from easy_tdx.chanlun.mmd import (
    _calc_sector_correlation_v50,
    _calc_multi_tf_resonance_v50,
    _calc_level_recursive_validation_v50,
    _calc_market_sentiment_fusion_v50,
)
from easy_tdx.chanlun.types import MMD, MMDType, BI, FX, FXType, CLKline, ZS, Direction
from datetime import datetime


def _make_mock_mmd(mmd_type: MMDType) -> MMD:
    """创建Mock MMD对象。"""
    return MMD(
        mmd_type=mmd_type,
        bi=None,
        zs=None,
        confidence=0.5,
        msg="test",
    )


def _make_mock_bi(direction: str = "up") -> BI:
    """创建Mock BI对象。"""
    start_fx = FX(
        fx_type=FXType.DI if direction == "up" else FXType.DING,
        k=CLKline(k_index=0, date=datetime.now(), open=100.0, close=100.0, high=101.0, low=99.0, amount=1000000.0),
        klines=[],
        val=100.0,
    )
    end_fx = FX(
        fx_type=FXType.DING if direction == "up" else FXType.DI,
        k=CLKline(k_index=10, date=datetime.now(), open=110.0, close=110.0, high=112.0, low=108.0, amount=1000000.0),
        klines=[],
        val=112.0,
    )
    return BI(start=start_fx, end=end_fx, direction=Direction.UP if direction == "up" else Direction.DOWN, high=112.0, low=99.0)


class TestSectorCorrelationV50:
    """条件140：板块联动分析测试。"""

    def test_positive_correlation_for_buy(self):
        """3买：价格上涨+量能放大 → 板块联动确认。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = _make_mock_bi("up")
        closes = [100.0 + i * 0.5 for i in range(30)]  # 上升趋势
        volumes = [1000000.0 * (1 + i * 0.05) for i in range(30)]  # 放量
        result = _calc_sector_correlation_v50(mmd, closes, volumes)
        assert result["correlated"] is True
        assert result["confidence_adjust"] == 0.02

    def test_negative_divergence_for_buy(self):
        """3买：价格上涨但量能萎缩 → 量价背离警告。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = _make_mock_bi("up")
        closes = [100.0 + i * 0.5 for i in range(30)]  # 上升趋势
        volumes = [1000000.0 * (1 - i * 0.03) for i in range(30)]  # 缩量
        result = _calc_sector_correlation_v50(mmd, closes, volumes)
        assert result["correlated"] is False
        assert result["confidence_adjust"] < 0

    def test_none_bi_returns_default(self):
        """bi为None时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = None
        result = _calc_sector_correlation_v50(mmd, [100.0] * 10, [1000000.0] * 10)
        assert result["correlated"] is False
        assert result["confidence_adjust"] == 0.0

    def test_insufficient_data_returns_default(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = _make_mock_bi("up")
        result = _calc_sector_correlation_v50(mmd, [100.0], [1000000.0])
        assert result["correlated"] is False
        assert result["confidence_adjust"] == 0.0


class TestMultiTFResonanceV50:
    """条件141：多时间框架共振验证测试。"""

    def test_strong_resonance_for_buy(self):
        """3买：多周期动量一致向上 → 共振确认。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = _make_mock_bi("up")
        # 长期上升趋势
        closes = [100.0 + i * 0.3 for i in range(60)]
        result = _calc_multi_tf_resonance_v50(mmd, closes)
        assert result["alignment_score"] >= 0.67
        assert result["confidence_adjust"] > 0

    def test_no_resonance_for_buy(self):
        """3买：多周期动量不一致 → 无共振。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = _make_mock_bi("up")
        # 震荡走势
        closes = [100.0 + 5 * (i % 2 == 0) for i in range(60)]
        result = _calc_multi_tf_resonance_v50(mmd, closes)
        assert result["alignment_score"] < 0.67

    def test_none_bi_returns_default(self):
        """bi为None时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = None
        result = _calc_multi_tf_resonance_v50(mmd, [100.0] * 60)
        assert result["resonant"] is False
        assert result["confidence_adjust"] == 0.0

    def test_insufficient_data_returns_default(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = _make_mock_bi("up")
        result = _calc_multi_tf_resonance_v50(mmd, [100.0] * 10)
        assert result["resonant"] is False


class TestLevelRecursiveValidationV50:
    """条件142：缠论级别递归验证测试。"""

    def test_strong_level_for_buy(self):
        """3买：中枢高度较大 → 递归验证通过。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 创建模拟中枢 - 使用较大地高度来触发normal验证
        zs = ZS(
            zg=120.0, zd=100.0, gg=125.0, dd=90.0,
            lines=[], direction="up"
        )
        mmd.zs = zs
        result = _calc_level_recursive_validation_v50(mmd, None)
        # 中枢高度占比 > 10% 时验证通过
        assert result["level_quality"] in ("strong", "normal")

    def test_weak_level_for_buy(self):
        """3买：中枢结构较弱 → 递归验证未通过。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        zs = ZS(
            zg=101.0, zd=100.0, gg=102.0, dd=99.0,
            lines=[], direction="up"
        )
        mmd.zs = zs
        result = _calc_level_recursive_validation_v50(mmd, None)
        assert result["level_quality"] == "weak"
        assert result["confidence_adjust"] < 0

    def test_none_zs_returns_default(self):
        """中枢为None时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.zs = None
        result = _calc_level_recursive_validation_v50(mmd, None)
        assert result["validated"] is False
        assert result["confidence_adjust"] == 0.0


class TestMarketSentimentFusionV50:
    """条件143：市场情绪指标融合测试。"""

    def test_oversold_for_buy(self):
        """3买：超卖情绪 + 放量 → 逆向买入机会。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 近期下跌趋势 + 放量
        closes = [100.0 - i * 0.5 for i in range(20)]
        volumes = [1000000.0 * (1 + i * 0.1) for i in range(20)]
        result = _calc_market_sentiment_fusion_v50(mmd, closes, volumes)
        assert result["sentiment"] == "oversold"
        assert result["confidence_adjust"] > 0

    def test_overbought_for_sell(self):
        """3卖：超买情绪 + 放量 → 逆向卖出机会。"""
        mmd = _make_mock_mmd(MMDType.SELL_3)
        # 近期上涨趋势 + 放量
        closes = [100.0 + i * 0.5 for i in range(20)]
        volumes = [1000000.0 * (1 + i * 0.1) for i in range(20)]
        result = _calc_market_sentiment_fusion_v50(mmd, closes, volumes)
        assert result["sentiment"] == "overbought"
        assert result["confidence_adjust"] > 0

    def test_neutral_sentiment(self):
        """中性情绪 → 无调整。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 震荡走势
        closes = [100.0 + 2 * (i % 2 == 0) for i in range(20)]
        volumes = [1000000.0] * 20
        result = _calc_market_sentiment_fusion_v50(mmd, closes, volumes)
        assert result["confidence_adjust"] == 0.0

    def test_insufficient_data_returns_default(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_market_sentiment_fusion_v50(mmd, [100.0], [1000000.0])
        assert result["sentiment"] == "neutral"
        assert result["confidence_adjust"] == 0.0


class TestFindMMDsV50Integration:
    """V50集成测试。"""

    def test_v50_fields_present_in_mmd(self):
        """V50字段应存在于MMD对象中。"""
        from easy_tdx.chanlun.types import MMD
        mmd = _make_mock_mmd(MMDType.BUY_3)
        assert hasattr(mmd, "_sector_correlation_v50")
        assert hasattr(mmd, "_multi_tf_resonance_v50")
        assert hasattr(mmd, "_level_recursive_validation_v50")
        assert hasattr(mmd, "_market_sentiment_fusion_v50")

    def test_v50_no_crash(self):
        """V50集成不崩溃。"""
        from easy_tdx.chanlun.mmd import find_mmds_v39
        # 基本集成测试，确保不会因缺少函数而崩溃
        assert callable(_calc_sector_correlation_v50)
        assert callable(_calc_multi_tf_resonance_v50)
        assert callable(_calc_level_recursive_validation_v50)
        assert callable(_calc_market_sentiment_fusion_v50)

    def test_v50_confidence_bounds(self):
        """V50置信度调整应在合理范围内。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = _make_mock_bi("up")
        closes = [100.0 + i * 0.3 for i in range(60)]
        volumes = [1000000.0] * 60

        # 测试各函数返回的置信度调整在合理范围内
        sector_result = _calc_sector_correlation_v50(mmd, closes, volumes)
        assert -0.05 <= sector_result["confidence_adjust"] <= 0.05

        mtf_result = _calc_multi_tf_resonance_v50(mmd, closes)
        assert -0.05 <= mtf_result["confidence_adjust"] <= 0.05

        sentiment_result = _calc_market_sentiment_fusion_v50(mmd, closes, volumes)
        assert -0.05 <= sentiment_result["confidence_adjust"] <= 0.05


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
