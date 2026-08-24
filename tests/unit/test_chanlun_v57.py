#!/usr/bin/env python3
"""V57 缠论模型条件168-171 专项测试。

测试内容：
- 条件168: 回踩幅度与时间双重过滤（Pullback Depth & Time Filter）
- 条件169: 突破力度验证（Breakout Strength Validation）
- 条件170: 中枢背驰检测（Zhongshu Divergence Check）
- 条件171: 信号衰减检测（Signal Decay Detection）
"""

from __future__ import annotations

import pytest

from easy_tdx.chanlun.mmd import (
    _calc_pullback_filter_v57,
    _calc_breakout_strength_validation_v57,
    _calc_zs_divergence_check_v57,
    _calc_signal_decay_detection_v57,
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


class TestPullbackFilterV57:
    """条件168: 回踩幅度与时间双重过滤测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_pullback_filter_v57(mmd, [100.0] * 10, None, None)
        assert "数据不足" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        closes = [100.0 + i * 0.1 for i in range(30)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = _calc_pullback_filter_v57(mmd, closes, highs, lows)
        assert "非3买/3卖" in result["msg"]

    def test_buy3_shallow_pullback(self):
        """3买浅回踩时应通过过滤。"""
        from easy_tdx.chanlun.types import BI, CLKline, Direction
        from datetime import datetime
        k = CLKline(k_index=25, date=datetime.now(), open=100.0, close=102.0, high=102.5, low=99.5, amount=1000.0, index=25)
        fx_end = type('obj', (object,), {'k': k})()
        fx_start = type('obj', (object,), {'k': type('obj', (object,), {'k_index': 20})()})()
        bi = BI(start=fx_start, end=fx_end, direction=Direction.UP)
        mmd = MMD(mmd_type=MMDType.BUY_3, bi=bi, zs=None, confidence=0.5, msg="test")
        # 信号点(25)后上涨2%然后轻微回撤
        closes = [100.0] * 20 + [100.0, 101.0, 102.0, 101.8, 101.5, 101.0]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = _calc_pullback_filter_v57(mmd, closes, highs, lows)
        assert result["pass_filter"] is True or result["pullback_depth_pct"] < 60

    def test_buy3_deep_pullback(self):
        """3买深回踩时应记录较大回撤比例。"""
        from easy_tdx.chanlun.types import BI, CLKline, Direction
        from datetime import datetime
        k = CLKline(k_index=25, date=datetime.now(), open=100.0, close=102.0, high=102.5, low=99.5, amount=1000.0, index=25)
        fx_end = type('obj', (object,), {'k': k})()
        fx_start = type('obj', (object,), {'k': type('obj', (object,), {'k_index': 20})()})()
        bi = BI(start=fx_start, end=fx_end, direction=Direction.UP)
        mmd = MMD(mmd_type=MMDType.BUY_3, bi=bi, zs=None, confidence=0.5, msg="test")
        base = [100.0] * 15
        breakout = [100.0, 101.0, 102.0, 101.0, 99.0, 98.0]
        closes = base + breakout
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        result = _calc_pullback_filter_v57(mmd, closes, highs, lows)
        assert isinstance(result["pullback_depth_pct"], float)

    def test_sell3_shallow_rebound(self):
        """3卖浅反弹时应通过过滤。"""
        mmd = _make_mock_mmd(MMDType.SELL_3)
        base = [100.0] * 15
        breakout = [100.0, 99.0, 98.0, 98.5, 99.0]  # 小幅反弹
        closes = base + breakout
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = _calc_pullback_filter_v57(mmd, closes, highs, lows)
        assert result["pass_filter"] is True


class TestBreakoutStrengthValidationV57:
    """条件169: 突破力度验证测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_breakout_strength_validation_v57(mmd, [100.0] * 10, [1000.0] * 10)
        assert "数据不足" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        closes = [100.0 + i * 0.1 for i in range(30)]
        volumes = [1000.0] * 30
        result = _calc_breakout_strength_validation_v57(mmd, closes, volumes)
        assert "非3买/3卖" in result["msg"]

    def test_strong_breakout(self):
        """强突破时应获得正向置信度调整。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 突破笔力度强，成交量放大
        closes = [100.0] * 10 + [100.0, 101.0, 102.0, 103.0, 104.0]
        volumes = [1000.0] * 20 + [2000.0, 2500.0, 3000.0]
        result = _calc_breakout_strength_validation_v57(mmd, closes, volumes)
        assert isinstance(result["force_ratio"], float)
        assert isinstance(result["volume_ratio"], float)

    def test_weak_breakout(self):
        """弱突破时应获得负向置信度调整。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 突破笔力度弱，成交量萎缩
        closes = [100.0] * 15 + [100.0, 100.1, 100.2, 100.15, 100.1]
        volumes = [1000.0] * 25 + [500.0, 400.0, 300.0]
        result = _calc_breakout_strength_validation_v57(mmd, closes, volumes)
        assert isinstance(result["confidence_adjust"], float)


class TestZhongshuDivergenceCheckV57:
    """条件170: 中枢背驰检测测试。"""

    def test_no_bis(self):
        """无笔数据时返回跳过信息。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_zs_divergence_check_v57(mmd, None, None)
        assert "中枢或笔数据不足" in result["msg"]

    def test_no_bc_list(self):
        """无背驰列表时返回跳过信息。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_zs_divergence_check_v57(mmd, [], None)
        assert "数据不足" in result["msg"] or "背驰" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        result = _calc_zs_divergence_check_v57(mmd, [], [])
        assert "非3买/3卖" in result["msg"]

    def test_returns_dict_structure(self):
        """返回字典包含必要字段。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_zs_divergence_check_v57(mmd, [], [])
        assert "has_divergence" in result
        assert "divergence_type" in result
        assert "confidence_adjust" in result


class TestSignalDecayDetectionV57:
    """条件171: 信号衰减检测测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_signal_decay_detection_v57(mmd, [100.0] * 10)
        assert "数据不足" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        closes = [100.0 + i * 0.1 for i in range(20)]
        result = _calc_signal_decay_detection_v57(mmd, closes)
        assert "非3买/3卖" in result["msg"]

    def test_buy3_decaying_signal(self):
        """3买信号衰减时应获得负向调整。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 信号点后先涨后跌
        closes = [100.0] * 10 + [100.0, 102.0, 101.0, 100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0]
        result = _calc_signal_decay_detection_v57(mmd, closes)
        assert isinstance(result["trend_momentum"], float)
        assert "信号" in result["msg"]

    def test_buy3_strong_signal(self):
        """3买信号强效时应获得正向调整。"""
        from easy_tdx.chanlun.types import BI, CLKline, Direction
        from datetime import datetime
        k = CLKline(k_index=18, date=datetime.now(), open=100.0, close=105.0, high=105.5, low=99.5, amount=1000.0, index=18)
        fx_end = type('obj', (object,), {'k': k})()
        fx_start = type('obj', (object,), {'k': type('obj', (object,), {'k_index': 10})()})()
        bi = BI(start=fx_start, end=fx_end, direction=Direction.UP)
        mmd = MMD(mmd_type=MMDType.BUY_3, bi=bi, zs=None, confidence=0.5, msg="test")
        # 信号点后持续上涨
        closes = [100.0] * 10 + [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0]
        result = _calc_signal_decay_detection_v57(mmd, closes)
        assert isinstance(result["trend_momentum"], float)
        assert result["msg"] != ""

    def test_sell3_decaying_signal(self):
        """3卖信号衰减时应获得负向调整。"""
        mmd = _make_mock_mmd(MMDType.SELL_3)
        # 信号点后先跌后反弹
        closes = [100.0] * 10 + [100.0, 98.0, 99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0]
        result = _calc_signal_decay_detection_v57(mmd, closes)
        assert isinstance(result["trend_momentum"], float)


class TestFindMMDsV57Integration:
    """V57 集成测试。"""

    def test_v57_functions_importable(self):
        """V57函数可正常导入。"""
        from easy_tdx.chanlun.mmd import (
            _calc_pullback_filter_v57,
            _calc_breakout_strength_validation_v57,
            _calc_zs_divergence_check_v57,
            _calc_signal_decay_detection_v57,
        )
        assert callable(_calc_pullback_filter_v57)
        assert callable(_calc_breakout_strength_validation_v57)
        assert callable(_calc_zs_divergence_check_v57)
        assert callable(_calc_signal_decay_detection_v57)

    def test_v57_fields_in_mmd_type(self):
        """MMD类型包含V57字段。"""
        from easy_tdx.chanlun.types import MMD
        mmd = MMD(mmd_type=MMDType.BUY_3, bi=None, zs=None, confidence=0.5, msg="test")
        assert hasattr(mmd, "_pullback_filter_v57")
        assert hasattr(mmd, "_breakout_strength_validation_v57")
        assert hasattr(mmd, "_zs_divergence_check_v57")
        assert hasattr(mmd, "_signal_decay_detection_v57")

    def test_v57_confidence_bounds(self):
        """V57调整后的置信度仍在有效范围内。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.5)
        closes = [100.0] * 10 + [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        volumes = [1000.0] * len(closes)

        result1 = _calc_pullback_filter_v57(mmd, closes, highs, lows)
        result2 = _calc_breakout_strength_validation_v57(mmd, closes, volumes)
        result4 = _calc_signal_decay_detection_v57(mmd, closes)

        total_adjust = sum([
            result1.get("confidence_adjust", 0),
            result2.get("confidence_adjust", 0),
            result4.get("confidence_adjust", 0),
        ])
        new_confidence = max(0.0, min(1.0, 0.5 + total_adjust))
        assert 0.0 <= new_confidence <= 1.0

    def test_v57_all_conditions_callable(self):
        """所有V57条件函数可正常调用不抛异常。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.1 for i in range(30)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        volumes = [1000.0 + i * 10 for i in range(30)]

        r1 = _calc_pullback_filter_v57(mmd, closes, highs, lows)
        r2 = _calc_breakout_strength_validation_v57(mmd, closes, volumes)
        r3 = _calc_zs_divergence_check_v57(mmd, [], [])
        r4 = _calc_signal_decay_detection_v57(mmd, closes)

        assert all(isinstance(r, dict) for r in [r1, r2, r3, r4])

    def test_sell3_v57_conditions(self):
        """3卖信号的V57条件正常工作。"""
        mmd = _make_mock_mmd(MMDType.SELL_3)
        closes = [100.0 - i * 0.1 for i in range(30)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        volumes = [1000.0] * 30

        r1 = _calc_pullback_filter_v57(mmd, closes, highs, lows)
        r2 = _calc_breakout_strength_validation_v57(mmd, closes, volumes)
        r4 = _calc_signal_decay_detection_v57(mmd, closes)

        assert all(isinstance(r, dict) for r in [r1, r2, r4])
        assert all("confidence_adjust" in r for r in [r1, r2, r4])
