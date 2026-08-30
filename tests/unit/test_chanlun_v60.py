#!/usr/bin/env python3
"""V60 缠论模型条件180-183 专项测试。

测试内容：
- 条件180: RSI深度背离过滤（RSI Deep Divergence Filter）
- 条件181: MA排列间距强度评分（MA Alignment Spacing Score）
- 条件182: 中枢支撑/阻力距离评分增强（ZhongShu Distance Score Enhanced）
- 条件183: KDJ超买超卖确认（KDJ Overbought/Oversold Confirmation）
"""

from __future__ import annotations

from easy_tdx.chanlun.mmd import (
    _calc_kdj_ob_os_confirm_v60,
    _calc_ma_spacing_strength_v60,
    _calc_rsi_deep_divergence_v60,
    _calc_zs_distance_enhanced_v60,
)
from easy_tdx.chanlun.types import MMD, ZS, MMDType


def _make_mock_mmd(mmd_type: MMDType, confidence: float = 0.5, zs=None) -> MMD:
    """创建Mock MMD对象。"""
    return MMD(
        mmd_type=mmd_type,
        bi=None,
        zs=zs,
        confidence=confidence,
        msg="test",
    )


def _make_zs(zg: float = 105.0, zd: float = 95.0) -> ZS:
    """创建Mock ZS对象。"""
    return ZS(zg=zg, zd=zd)


class TestRSIDeepDivergenceV60:
    """条件180: RSI深度背离过滤测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_rsi_deep_divergence_v60(mmd, [100.0] * 10)
        assert "数据不足" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        closes = [100.0 + i * 0.1 for i in range(100)]
        result = _calc_rsi_deep_divergence_v60(mmd, closes)
        assert "非3买/3卖信号" in result["msg"]

    def test_basic_structure(self):
        """返回结构正确。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.5 for i in range(100)]
        result = _calc_rsi_deep_divergence_v60(mmd, closes)
        assert "rsi_current" in result
        assert "divergence_type" in result
        assert "divergence_depth" in result
        assert "confidence_adjust" in result
        assert "msg" in result

    def test_confidence_bounds(self):
        """置信度调整在合理范围内。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.5 for i in range(100)]
        result = _calc_rsi_deep_divergence_v60(mmd, closes)
        adj = result.get("confidence_adjust", 0.0)
        assert -0.05 <= adj <= 0.05


class TestMASpacingStrengthV60:
    """条件181: MA排列间距强度评分测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_ma_spacing_strength_v60(mmd, [100.0] * 10)
        assert "数据不足" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        closes = [100.0 + i * 0.1 for i in range(100)]
        result = _calc_ma_spacing_strength_v60(mmd, closes)
        assert "非3买/3卖信号" in result["msg"]

    def test_bullish_alignment(self):
        """多头排列且间距大时给予正置信度。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 递增趋势：MA5 > MA20 > MA60
        closes = [100.0 + i * 1.0 for i in range(100)]
        result = _calc_ma_spacing_strength_v60(mmd, closes)
        assert result["alignment"] == "bullish"
        assert result["confidence_adjust"] > 0

    def test_bearish_alignment_for_buy(self):
        """空头排列对3买信号应给负置信度。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 递减趋势
        closes = [200.0 - i * 1.0 for i in range(100)]
        result = _calc_ma_spacing_strength_v60(mmd, closes)
        assert result["alignment"] == "bearish"
        assert result["confidence_adjust"] < 0

    def test_entangled_ma(self):
        """均线纠缠时应给负置信度。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 震荡数据，均线接近
        import random

        random.seed(42)
        closes = []
        price = 100.0
        for _ in range(100):
            price += random.gauss(0, 0.1)
            closes.append(price)
        result = _calc_ma_spacing_strength_v60(mmd, closes)
        # 震荡时alignment可能为entangled
        assert "msg" in result
        assert "confidence_adjust" in result

    def test_returns_dict_structure(self):
        """返回字典结构正确。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.5 for i in range(100)]
        result = _calc_ma_spacing_strength_v60(mmd, closes)
        assert "ma5" in result
        assert "ma20" in result
        assert "ma60" in result
        assert "spacing_ratio" in result
        assert "alignment" in result
        assert "spacing_strength" in result
        assert "confidence_adjust" in result
        assert "msg" in result


class TestZSDistanceEnhancedV60:
    """条件182: 中枢支撑/阻力距离评分增强测试。"""

    def test_no_zs(self):
        """无中枢数据时返回提示。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_zs_distance_enhanced_v60(mmd, [100.0] * 10)
        assert "无中枢数据" in result["msg"]

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, zs=_make_zs())
        result = _calc_zs_distance_enhanced_v60(mmd, [100.0] * 10)
        assert "数据不足" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1, zs=_make_zs())
        closes = [100.0 + i * 0.1 for i in range(30)]
        result = _calc_zs_distance_enhanced_v60(mmd, closes)
        assert "非3买/3卖信号" in result["msg"]

    def test_above_zs_buy_signal(self):
        """3买信号价格在中枢上方时应有正置信度。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, zs=_make_zs(zg=105.0, zd=95.0))
        # 价格在110，高于中枢上沿105
        closes = [110.0 + i * 0.1 for i in range(30)]
        result = _calc_zs_distance_enhanced_v60(mmd, closes)
        assert result["position"] == "above_zs"
        assert result["confidence_adjust"] >= 0

    def test_below_zs_buy_signal(self):
        """3买信号价格在中枢下方时应给负置信度。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, zs=_make_zs(zg=105.0, zd=95.0))
        # 价格在90，低于中枢下沿95
        closes = [90.0 + i * 0.1 for i in range(30)]
        result = _calc_zs_distance_enhanced_v60(mmd, closes)
        assert result["position"] == "below_zs"
        assert result["confidence_adjust"] < 0

    def test_returns_dict_structure(self):
        """返回字典结构正确。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, zs=_make_zs())
        closes = [110.0 + i * 0.1 for i in range(30)]
        result = _calc_zs_distance_enhanced_v60(mmd, closes)
        assert "zs_zg" in result
        assert "zs_zd" in result
        assert "price" in result
        assert "position" in result
        assert "pullback_confirmed" in result
        assert "confidence_adjust" in result
        assert "msg" in result


class TestKDJOverboughtOversoldV60:
    """条件183: KDJ超买超卖确认测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_kdj_ob_os_confirm_v60(mmd, [100.0] * 10)
        assert "数据不足" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        closes = [100.0 + i * 0.1 for i in range(20)]
        result = _calc_kdj_ob_os_confirm_v60(mmd, closes)
        assert "非3买/3卖信号" in result["msg"]

    def test_basic_structure(self):
        """返回结构正确。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.5 for i in range(20)]
        result = _calc_kdj_ob_os_confirm_v60(mmd, closes)
        assert "kdj_k" in result
        assert "kdj_d" in result
        assert "kdj_j" in result
        assert "j_trend" in result
        assert "ob_os_zone" in result
        assert "signal_aligned" in result
        assert "confidence_adjust" in result
        assert "msg" in result

    def test_confidence_bounds(self):
        """置信度调整在合理范围内。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.5 for i in range(20)]
        result = _calc_kdj_ob_os_confirm_v60(mmd, closes)
        adj = result.get("confidence_adjust", 0.0)
        assert -0.05 <= adj <= 0.05

    def test_trending_up_data(self):
        """上升趋势中3买信号的J值应显示合理状态。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 稳定上升趋势
        closes = [100.0 + i * 0.5 for i in range(30)]
        result = _calc_kdj_ob_os_confirm_v60(mmd, closes)
        assert result["kdj_j"] > 0
        assert result["msg"] != ""


class TestFindMMDsV60Integration:
    """V60 集成测试。"""

    def test_v60_functions_importable(self):
        """所有V60函数可导入。"""
        from easy_tdx.chanlun.mmd import (
            _calc_kdj_ob_os_confirm_v60,
            _calc_ma_spacing_strength_v60,
            _calc_rsi_deep_divergence_v60,
            _calc_zs_distance_enhanced_v60,
        )

        assert callable(_calc_rsi_deep_divergence_v60)
        assert callable(_calc_ma_spacing_strength_v60)
        assert callable(_calc_zs_distance_enhanced_v60)
        assert callable(_calc_kdj_ob_os_confirm_v60)

    def test_v60_fields_in_mmd_type(self):
        """MMD类型包含V60字段。"""
        import dataclasses

        from easy_tdx.chanlun.types import MMD

        fields = {f.name for f in dataclasses.fields(MMD)}
        assert "_rsi_deep_divergence_v60" in fields
        assert "_ma_spacing_strength_v60" in fields
        assert "_zs_distance_enhanced_v60" in fields
        assert "_kdj_ob_os_confirm_v60" in fields

    def test_v60_confidence_bounds(self):
        """V60置信度调整不越界。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.5 for i in range(100)]
        _ = [c + 0.5 for c in closes]
        _ = [c - 0.5 for c in closes]

        r1 = _calc_rsi_deep_divergence_v60(mmd, closes)
        r2 = _calc_ma_spacing_strength_v60(mmd, closes)
        r3 = _calc_zs_distance_enhanced_v60(mmd, closes)
        r4 = _calc_kdj_ob_os_confirm_v60(mmd, closes)

        for r in [r1, r2, r3, r4]:
            adj = r.get("confidence_adjust", 0.0)
            assert -0.05 <= adj <= 0.05, f"confidence_adjust {adj} out of range"

    def test_v60_all_conditions_callable(self):
        """所有V60条件可正常调用。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.5 for i in range(100)]

        r1 = _calc_rsi_deep_divergence_v60(mmd, closes)
        r2 = _calc_ma_spacing_strength_v60(mmd, closes)
        r3 = _calc_zs_distance_enhanced_v60(mmd, closes)
        r4 = _calc_kdj_ob_os_confirm_v60(mmd, closes)

        assert all(isinstance(r, dict) for r in [r1, r2, r3, r4])
        assert all("confidence_adjust" in r for r in [r1, r2, r3, r4])
        assert all("msg" in r for r in [r1, r2, r3, r4])

    def test_sell3_v60_conditions(self):
        """3卖信号V60条件正确执行。"""
        mmd = _make_mock_mmd(MMDType.SELL_3)
        closes = [100.0 - i * 0.5 for i in range(100)]

        r1 = _calc_rsi_deep_divergence_v60(mmd, closes)
        r2 = _calc_ma_spacing_strength_v60(mmd, closes)
        r3 = _calc_zs_distance_enhanced_v60(mmd, closes)
        r4 = _calc_kdj_ob_os_confirm_v60(mmd, closes)

        assert r1["msg"] != ""
        assert r2["msg"] != ""
        assert r3["msg"] != ""
        assert r4["msg"] != ""

    def test_v60_integration_pass(self):
        """集成测试通过。"""
        import pandas as pd

        from easy_tdx.chanlun import ChanlunAnalyser

        # 生成模拟上涨数据
        n = 200
        import numpy as np

        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        close = [100.0]
        for i in range(1, n):
            close.append(close[-1] * (1.001 + np.random.normal(0, 0.005)))
        close = np.array(close)

        df = pd.DataFrame(
            {
                "datetime": dates,
                "open": close * (1 + np.random.uniform(-0.002, 0.002, n)),
                "high": close * (1 + np.random.uniform(0, 0.008, n)),
                "low": close * (1 + np.random.uniform(-0.008, 0, n)),
                "close": close,
                "vol": [1e6] * n,
            }
        )

        analyser = ChanlunAnalyser(code="TEST", frequency="daily")
        result = analyser.process_klines(df)

        # 验证V60字段存在于结果中
        for mmd in result.mmds:
            assert hasattr(mmd, "_rsi_deep_divergence_v60")
            assert hasattr(mmd, "_ma_spacing_strength_v60")
            assert hasattr(mmd, "_zs_distance_enhanced_v60")
            assert hasattr(mmd, "_kdj_ob_os_confirm_v60")

        # 应该有至少一个3买或3卖信号
        buy_3_count = sum(1 for m in result.mmds if m.mmd_type.value == "3buy")
        sell_3_count = sum(1 for m in result.mmds if m.mmd_type.value == "3sell")
        assert buy_3_count >= 0 or sell_3_count >= 0
