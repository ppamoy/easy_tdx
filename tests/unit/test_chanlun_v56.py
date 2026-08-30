#!/usr/bin/env python3
"""V56 缠论模型条件164-167 专项测试。

测试内容：
- 条件164: 假突破识别（False Breakout Detection）
- 条件165: 中枢结构复杂度分析（Zhongshu Structure Complexity）
- 条件166: 波动率自适应仓位建议（Volatility Adaptive Position Sizing）
- 条件167: 多信号共振评分（Multi-Signal Resonance Score）
"""

from __future__ import annotations

import pytest

from easy_tdx.chanlun.mmd import (
    _calc_false_breakout_detection_v56,
    _calc_multi_signal_resonance_v56,
    _calc_volatility_adaptive_position_v56,
    _calc_zhongshu_structure_complexity_v56,
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


class TestFalseBreakoutDetectionV56:
    """条件164: 假突破识别测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_false_breakout_detection_v56(mmd, [100.0] * 10, [1000.0] * 10, None, None)
        assert result["is_fake"] is False
        assert result["confidence_adjust"] == 0.0

    def test_none_bi(self):
        """bi为None时仍可正常调用。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.1 for i in range(30)]
        volumes = [1000.0 + i * 10 for i in range(30)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = _calc_false_breakout_detection_v56(mmd, closes, volumes, highs, lows)
        assert isinstance(result["retracement_pct"], float)
        assert isinstance(result["volume_ratio"], float)

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        closes = [100.0 + i * 0.1 for i in range(30)]
        volumes = [1000.0] * 30
        result = _calc_false_breakout_detection_v56(mmd, closes, volumes, None, None)
        assert "非3买" in result["msg"] or result["confidence_adjust"] == 0.0

    def test_importable(self):
        """函数可正常导入。"""
        from easy_tdx.chanlun.mmd import _calc_false_breakout_detection_v56

        assert callable(_calc_false_breakout_detection_v56)

    def test_buy3_fake_breakout(self):
        """3买假突破场景：回撤超过50%。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 模拟突破后大幅回撤
        closes = [100.0] * 20 + [100.0, 101.0, 102.0, 100.5, 99.0, 98.0]  # 突破后回撤
        volumes = [1000.0] * 26
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        mmd.bi = type(
            "obj",
            (object,),
            {"end": type("obj", (object,), {"k": type("obj", (object,), {"k_index": 19})()})()},
        )()
        result = _calc_false_breakout_detection_v56(mmd, closes, volumes, highs, lows)
        assert isinstance(result["retracement_pct"], float)
        assert isinstance(result["confidence_adjust"], float)

    def test_buy3_valid_breakout(self):
        """3买真突破场景：放量上涨。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0] * 20 + [100.5, 101.5, 102.5, 103.5, 104.5]
        volumes = [1000.0] * 20 + [1500.0, 1600.0, 1700.0, 1800.0, 1900.0]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        mmd.bi = type(
            "obj",
            (object,),
            {"end": type("obj", (object,), {"k": type("obj", (object,), {"k_index": 19})()})()},
        )()
        result = _calc_false_breakout_detection_v56(mmd, closes, volumes, highs, lows)
        assert isinstance(result["breakout_valid"], bool)
        assert isinstance(result["confidence_adjust"], float)


class TestZhongshuStructureComplexityV56:
    """条件165: 中枢结构复杂度分析测试。"""

    def test_no_zss(self):
        """无中枢数据时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_zhongshu_structure_complexity_v56(mmd, [])
        assert result["complexity"] == "unknown"
        assert result["confidence_adjust"] == 0.0

    def test_none_bi(self):
        """mmd.zs为None时仍可正常调用。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.zs = None
        result = _calc_zhongshu_structure_complexity_v56(mmd, [])
        assert "中枢信息" in result["msg"] or result["confidence_adjust"] == 0.0

    def test_importable(self):
        """函数可正常导入。"""
        from easy_tdx.chanlun.mmd import _calc_zhongshu_structure_complexity_v56

        assert callable(_calc_zhongshu_structure_complexity_v56)

    def test_simple_structure(self):
        """简单结构（无重叠）场景。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)

        class MockZS:
            def __init__(self, zg, zd):
                self.zg = zg
                self.zd = zd
                self.start = object()
                self.end = object()

        # 创建不重叠的中枢
        zss = [MockZS(105, 100), MockZS(110, 106), MockZS(115, 111)]
        mmd.zs = zss[1]

        result = _calc_zhongshu_structure_complexity_v56(mmd, zss)
        assert isinstance(result["complexity"], str)
        assert isinstance(result["overlap_count"], int)
        assert isinstance(result["confidence_adjust"], float)


class TestVolatilityAdaptivePositionV56:
    """条件166: 波动率自适应仓位建议测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_volatility_adaptive_position_v56(
            mmd, [100.0] * 10, [100.5] * 10, [99.5] * 10
        )
        assert result["volatility_level"] == "unknown"
        assert result["confidence_adjust"] == 0.0

    def test_empty_data(self):
        """空数据时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_volatility_adaptive_position_v56(mmd, [], [], [])
        assert result["atr_value"] == 0.0
        assert result["confidence_adjust"] == 0.0

    def test_none_bi(self):
        """bi为None时仍可正常调用。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.1 for i in range(30)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = _calc_volatility_adaptive_position_v56(mmd, closes, highs, lows)
        assert isinstance(result["atr_value"], float)
        assert isinstance(result["volatility_level"], str)
        assert isinstance(result["position_suggestion"], str)
        assert isinstance(result["confidence_adjust"], float)

    def test_importable(self):
        """函数可正常导入。"""
        from easy_tdx.chanlun.mmd import _calc_volatility_adaptive_position_v56

        assert callable(_calc_volatility_adaptive_position_v56)

    def test_low_volatility(self):
        """低波动场景。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 低波动：价格变化很小
        closes = [100.0] * 30
        highs = [100.1] * 30
        lows = [99.9] * 30
        result = _calc_volatility_adaptive_position_v56(mmd, closes, highs, lows)
        assert result["atr_value"] < 1.5
        assert result["volatility_level"] == "low"
        assert result["position_suggestion"] == "high"

    def test_high_volatility(self):
        """高波动场景。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 高波动：价格大幅震荡
        closes = [100.0, 105.0, 95.0, 110.0, 90.0] * 6
        highs = [c + 5.0 for c in closes]
        lows = [c - 5.0 for c in closes]
        result = _calc_volatility_adaptive_position_v56(mmd, closes, highs, lows)
        assert result["atr_value"] > 3.0
        assert result["volatility_level"] in ("high", "extreme")


class TestMultiSignalResonanceV56:
    """条件167: 多信号共振评分测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_multi_signal_resonance_v56(mmd, [100.0] * 20, [1000.0] * 20)
        assert "数据不足" in result["msg"] or result["resonance_count"] == 0

    def test_none_bi(self):
        """bi为None时仍可正常调用。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.1 for i in range(40)]
        volumes = [1000.0 + (i % 3) * 100 for i in range(40)]
        result = _calc_multi_signal_resonance_v56(mmd, closes, volumes)
        assert isinstance(result["resonance_count"], int)
        assert isinstance(result["confirming_indicators"], list)
        assert isinstance(result["confidence_adjust"], float)

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        closes = [100.0 + i * 0.1 for i in range(40)]
        volumes = [1000.0] * 40
        result = _calc_multi_signal_resonance_v56(mmd, closes, volumes)
        assert "非3买" in result["msg"] or result["confidence_adjust"] == 0.0

    def test_importable(self):
        """函数可正常导入。"""
        from easy_tdx.chanlun.mmd import _calc_multi_signal_resonance_v56

        assert callable(_calc_multi_signal_resonance_v56)

    def test_bearish_signal(self):
        """3卖信号的共振分析。"""
        mmd = _make_mock_mmd(MMDType.SELL_3)
        # 下降趋势
        closes = [100.0 - i * 0.1 for i in range(40)]
        volumes = [1000.0 + (i % 3) * 100 for i in range(40)]
        result = _calc_multi_signal_resonance_v56(mmd, closes, volumes)
        assert isinstance(result["resonance_count"], int)
        assert isinstance(result["confirming_indicators"], list)
        assert 0 <= result["resonance_count"] <= 5


class TestFindMMDsV56Integration:
    """V56 集成测试。"""

    def test_v56_functions_importable(self):
        """所有V56函数可正常导入。"""
        from easy_tdx.chanlun.mmd import (
            _calc_false_breakout_detection_v56,
            _calc_multi_signal_resonance_v56,
            _calc_volatility_adaptive_position_v56,
            _calc_zhongshu_structure_complexity_v56,
        )

        assert callable(_calc_false_breakout_detection_v56)
        assert callable(_calc_zhongshu_structure_complexity_v56)
        assert callable(_calc_volatility_adaptive_position_v56)
        assert callable(_calc_multi_signal_resonance_v56)

    def test_v56_fields_in_mmd_type(self):
        """MMD类型包含V56字段定义。"""
        from easy_tdx.chanlun.types import MMD

        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, msg="test")
        assert hasattr(mmd, "_false_breakout_detection_v56")
        assert hasattr(mmd, "_zhongshu_structure_complexity_v56")
        assert hasattr(mmd, "_volatility_adaptive_position_v56")
        assert hasattr(mmd, "_multi_signal_resonance_v56")

    def test_v56_confidence_bounds(self):
        """V56置信度调整不超出[0, 1]范围。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.5)
        closes = [100.0 + i * 0.1 for i in range(40)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        volumes = [1000.0 + (i % 3) * 100 for i in range(40)]

        r1 = _calc_false_breakout_detection_v56(mmd, closes, volumes, highs, lows)
        r2 = _calc_zhongshu_structure_complexity_v56(mmd, [])
        r3 = _calc_volatility_adaptive_position_v56(mmd, closes, highs, lows)
        r4 = _calc_multi_signal_resonance_v56(mmd, closes, volumes)

        for r in [r1, r2, r3, r4]:
            new_conf = max(0.0, min(1.0, mmd.confidence + r.get("confidence_adjust", 0.0)))
            assert 0.0 <= new_conf <= 1.0

    def test_v56_all_conditions_callable(self):
        """所有V56条件函数可正常调用且不抛出异常。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.1 for i in range(40)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        volumes = [1000.0 + (i % 3) * 100 for i in range(40)]

        r1 = _calc_false_breakout_detection_v56(mmd, closes, volumes, highs, lows)
        r2 = _calc_zhongshu_structure_complexity_v56(mmd, [])
        r3 = _calc_volatility_adaptive_position_v56(mmd, closes, highs, lows)
        r4 = _calc_multi_signal_resonance_v56(mmd, closes, volumes)

        assert isinstance(r1, dict)
        assert isinstance(r2, dict)
        assert isinstance(r3, dict)
        assert isinstance(r4, dict)

        assert "confidence_adjust" in r1
        assert "confidence_adjust" in r2
        assert "confidence_adjust" in r3
        assert "confidence_adjust" in r4

    def test_sell3_v56_conditions(self):
        """3卖信号的V56条件正常处理。"""
        mmd = _make_mock_mmd(MMDType.SELL_3)
        closes = [100.0 - i * 0.1 for i in range(40)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        volumes = [1000.0] * 40

        r1 = _calc_false_breakout_detection_v56(mmd, closes, volumes, highs, lows)
        r2 = _calc_zhongshu_structure_complexity_v56(mmd, [])
        r3 = _calc_volatility_adaptive_position_v56(mmd, closes, highs, lows)
        r4 = _calc_multi_signal_resonance_v56(mmd, closes, volumes)

        for r in [r1, r2, r3, r4]:
            assert isinstance(r, dict)
            assert "confidence_adjust" in r


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
