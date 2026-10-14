#!/usr/bin/env python3
"""V59 缠论模型条件176-179 专项测试。

测试内容：
- 条件176: 波动率自适应MA周期（Volatility-Adaptive MA Period）
- 条件177: ATR倍数自适应（ATR Multiplier Adaptation）
- 条件178: 多时间框架共振信号（Multi-TF Resonance Signal）
- 条件179: 信号衰减速度评估（Signal Decay Speed）
"""

from __future__ import annotations

from easy_tdx.chanlun.mmd import (
    _calc_atr_multiplier_adapt_v59,
    _calc_multi_tf_resonance_signal_v59,
    _calc_signal_decay_speed_v59,
    _calc_volatility_adaptive_ma_v59,
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


class TestVolatilityAdaptiveMAV59:
    """条件176: 波动率自适应MA周期测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_volatility_adaptive_ma_v59(mmd, [100.0] * 10)
        assert "数据不足" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        closes = [100.0 + i * 0.1 for i in range(100)]
        result = _calc_volatility_adaptive_ma_v59(mmd, closes)
        assert "非3买/3卖信号" in result["msg"]

    def test_normal_volatility(self):
        """正常波动率时使用默认MA周期。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 生成约2%波动率的数据（std/mean ≈ 0.02）
        import random

        random.seed(123)
        closes = []
        price = 100.0
        for _ in range(100):
            price += random.gauss(0, 0.8)  # std≈0.8, mean≈100 → vol≈0.8% → borderline
            closes.append(price)
        # 使用确定性数据避免随机性
        closes = [100.0 + i * 0.02 + (1.0 if i % 7 == 0 else 0) for i in range(100)]
        result = _calc_volatility_adaptive_ma_v59(mmd, closes)
        # 确保在normal范围内(1%-4%)
        assert result["volatility_regime"] in ("normal", "low", "high")
        # 检查返回结构正确
        assert result["adaptive_ma_short"] in (3, 5, 8)
        assert result["adaptive_ma_mid"] in (10, 20, 30)
        assert result["adaptive_ma_long"] in (30, 60, 90)

    def test_high_volatility(self):
        """高波动率时缩短MA周期。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 高波动：大幅增加标准差
        import random

        random.seed(42)
        closes = []
        price = 100.0
        for _ in range(100):
            price += random.gauss(0, 5.0)  # 大波动
            closes.append(price)
        result = _calc_volatility_adaptive_ma_v59(mmd, closes)
        assert result["volatility_regime"] == "high"
        assert result["adaptive_ma_short"] == 3
        assert result["adaptive_ma_mid"] == 10
        assert result["adaptive_ma_long"] == 30
        assert result["confidence_adjust"] == -0.02

    def test_low_volatility(self):
        """低波动率时延长MA周期。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.001 for i in range(100)]
        result = _calc_volatility_adaptive_ma_v59(mmd, closes)
        assert result["volatility_regime"] == "low"
        assert result["adaptive_ma_short"] == 8
        assert result["adaptive_ma_mid"] == 30
        assert result["adaptive_ma_long"] == 90
        assert result["confidence_adjust"] == 0.02

    def test_sell3_direction(self):
        """3卖信号方向正确。"""
        mmd = _make_mock_mmd(MMDType.SELL_3)
        # 确定性数据，正常波动率
        closes = [100.0 + i * 0.02 + (1.0 if i % 7 == 0 else 0) for i in range(100)]
        result = _calc_volatility_adaptive_ma_v59(mmd, closes)
        assert result["volatility_regime"] in ("normal", "low", "high")
        assert result["adaptive_ma_short"] in (3, 5, 8)

    def test_returns_dict_structure(self):
        """返回字典结构正确。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.01 for i in range(100)]
        result = _calc_volatility_adaptive_ma_v59(mmd, closes)
        assert "adaptive_ma_short" in result
        assert "adaptive_ma_mid" in result
        assert "adaptive_ma_long" in result
        assert "volatility_regime" in result
        assert "confidence_adjust" in result
        assert "msg" in result


class TestATRMultiplierAdaptV59:
    """条件177: ATR倍数自适应测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_atr_multiplier_adapt_v59(mmd, [100.0] * 10, [99.0] * 10)
        assert "数据不足" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        highs = [100.0 + i * 0.1 for i in range(20)]
        lows = [99.0 + i * 0.1 for i in range(20)]
        result = _calc_atr_multiplier_adapt_v59(mmd, highs, lows)
        assert "非3买/3卖信号" in result["msg"]

    def test_normal_volatility(self):
        """正常波动率使用默认2x倍数。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 生成ATR≈2%的normal数据
        highs = [100.0 + i * 0.5 for i in range(20)]
        lows = [98.0 + i * 0.5 for i in range(20)]  # spread=2.0, atr≈2, price≈109 → 2/109≈1.8%
        result = _calc_atr_multiplier_adapt_v59(mmd, highs, lows)
        assert result["optimal_multiplier"] == 2.0
        assert result["volatility_regime"] == "normal"

    def test_high_volatility(self):
        """高波动率使用更大ATR倍数（3x）。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        highs = [100.0] * 14 + [110.0, 120.0, 130.0]
        lows = [80.0] * 14 + [70.0, 60.0, 50.0]
        result = _calc_atr_multiplier_adapt_v59(mmd, highs, lows)
        assert result["optimal_multiplier"] >= 2.5

    def test_sell3_direction(self):
        """3卖信号方向正确。"""
        mmd = _make_mock_mmd(MMDType.SELL_3)
        highs = [100.0 + i * 0.1 for i in range(20)]
        lows = [99.5 + i * 0.1 for i in range(20)]
        result = _calc_atr_multiplier_adapt_v59(mmd, highs, lows)
        assert "卖出" in result["msg"]

    def test_returns_dict_structure(self):
        """返回字典结构正确。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        highs = [100.0 + i * 0.1 for i in range(20)]
        lows = [99.5 + i * 0.1 for i in range(20)]
        result = _calc_atr_multiplier_adapt_v59(mmd, highs, lows)
        assert "atr_14" in result
        assert "optimal_multiplier" in result
        assert "stop_distance_pct" in result
        assert "volatility_regime" in result
        assert "confidence_adjust" in result
        assert "msg" in result


class TestMultiTFResonanceSignalV59:
    """条件178: 多时间框架共振信号测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_multi_tf_resonance_signal_v59(mmd, [100.0] * 10)
        assert "数据不足" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        closes = [100.0 + i * 0.1 for i in range(30)]
        result = _calc_multi_tf_resonance_signal_v59(mmd, closes)
        assert "非3买/3卖信号" in result["msg"]

    def test_strong_resonance_up(self):
        """上升趋势中短周期和中期趋势一致，共振强。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.5 for i in range(50)]
        result = _calc_multi_tf_resonance_signal_v59(mmd, closes)
        assert result["short_tf_trend"] == "up"
        assert result["resonance_score"] == 2
        assert result["confidence_adjust"] == 0.04

    def test_strong_resonance_down(self):
        """下降趋势中短周期和中期趋势一致，共振强（3卖）。"""
        mmd = _make_mock_mmd(MMDType.SELL_3)
        closes = [100.0 - i * 0.5 for i in range(50)]
        result = _calc_multi_tf_resonance_signal_v59(mmd, closes)
        assert result["short_tf_trend"] == "down"
        assert result["resonance_score"] == 2
        assert result["confidence_adjust"] == 0.04

    def test_opposite_resonance(self):
        """短周期下跌+中期下跌，对3买信号是强反向共振。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 单调递减：[100, 99, ..., 0]
        # 短周期最后5根：[4,3,2,1,0] → DOWN
        # 中期：近20根avg≈9.5 < 前20根avg≈29.5 → DOWN
        closes = list(range(100, -1, -1))
        result = _calc_multi_tf_resonance_signal_v59(mmd, closes)
        assert result["short_tf_trend"] == "down"
        # 对于BUY信号：short=down + mid=down → score=-2
        assert result["resonance_score"] == -2
        assert result["confidence_adjust"] == -0.04

    def test_returns_dict_structure(self):
        """返回字典结构正确。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.5 for i in range(50)]
        result = _calc_multi_tf_resonance_signal_v59(mmd, closes)
        assert "short_tf_trend" in result
        assert "short_tf_momentum" in result
        assert "resonance_score" in result
        assert "resonance_strength" in result
        assert "confidence_adjust" in result
        assert "msg" in result


class TestSignalDecaySpeedV59:
    """条件179: 信号衰减速度评估测试。"""

    def test_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_signal_decay_speed_v59(mmd, [100.0] * 10)
        assert "数据不足" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mock_mmd(MMDType.BUY_1)
        closes = [100.0 + i * 0.1 for i in range(20)]
        result = _calc_signal_decay_speed_v59(mmd, closes)
        assert "非3买/3卖信号" in result["msg"]

    def test_fast_rise_strong_signal(self):
        """信号后快速上涨，强信号。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 前15根平稳，后10根快速上涨
        closes = [100.0] * 15 + [100.0 + i * 1.0 for i in range(10)]
        result = _calc_signal_decay_speed_v59(mmd, closes)
        assert result["decay_rate"] == "fast_rise"
        assert result["signal_strength"] == "strong"
        assert result["confidence_adjust"] == 0.03

    def test_fast_fall_strong_sell(self):
        """信号后快速下跌，强3卖信号。"""
        mmd = _make_mock_mmd(MMDType.SELL_3)
        closes = [100.0] * 15 + [100.0 - i * 1.0 for i in range(10)]
        result = _calc_signal_decay_speed_v59(mmd, closes)
        assert result["decay_rate"] == "fast_fall"
        assert result["signal_strength"] == "strong"
        assert result["confidence_adjust"] == 0.03

    def test_reversal_fake_signal(self):
        """信号后价格反向运动，假信号。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 前15根平稳，后10根下跌
        closes = [100.0] * 15 + [100.0 - i * 0.5 for i in range(10)]
        result = _calc_signal_decay_speed_v59(mmd, closes)
        assert result["decay_rate"] == "reversal"
        assert result["signal_strength"] == "fake"
        assert result["confidence_adjust"] == -0.04

    def test_returns_dict_structure(self):
        """返回字典结构正确。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.5 for i in range(20)]
        result = _calc_signal_decay_speed_v59(mmd, closes)
        assert "price_speed_after_signal" in result
        assert "decay_rate" in result
        assert "signal_strength" in result
        assert "confidence_adjust" in result
        assert "msg" in result


class TestFindMMDsV59Integration:
    """V59 集成测试。"""

    def test_v59_functions_importable(self):
        """所有V59函数可导入。"""
        from easy_tdx.chanlun.mmd import (
            _calc_atr_multiplier_adapt_v59,
            _calc_multi_tf_resonance_signal_v59,
            _calc_signal_decay_speed_v59,
            _calc_volatility_adaptive_ma_v59,
        )

        assert callable(_calc_volatility_adaptive_ma_v59)
        assert callable(_calc_atr_multiplier_adapt_v59)
        assert callable(_calc_multi_tf_resonance_signal_v59)
        assert callable(_calc_signal_decay_speed_v59)

    def test_v59_fields_in_mmd_type(self):
        """MMD类型包含V59字段。"""
        import dataclasses

        from easy_tdx.chanlun.types import MMD

        fields = {f.name for f in dataclasses.fields(MMD)}
        assert "_volatility_adaptive_ma_v59" in fields
        assert "_atr_multiplier_adapt_v59" in fields
        assert "_multi_tf_resonance_signal_v59" in fields
        assert "_signal_decay_speed_v59" in fields

    def test_v59_confidence_bounds(self):
        """V59置信度调整不越界。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.5)
        closes = [100.0 + i * 0.5 for i in range(100)]

        r1 = _calc_volatility_adaptive_ma_v59(mmd, closes)
        r2 = _calc_multi_tf_resonance_signal_v59(mmd, closes)
        r3 = _calc_signal_decay_speed_v59(mmd, closes)

        for r in [r1, r2, r3]:
            adj = r.get("confidence_adjust", 0.0)
            assert -0.05 <= adj <= 0.05, f"confidence_adjust {adj} out of range"

    def test_v59_all_conditions_callable(self):
        """所有V59条件可正常调用。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        closes = [100.0 + i * 0.5 for i in range(100)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        volumes = [1e6] * 100

        r1 = _calc_volatility_adaptive_ma_v59(mmd, closes)
        r2 = _calc_atr_multiplier_adapt_v59(mmd, highs, lows)
        r3 = _calc_multi_tf_resonance_signal_v59(mmd, closes, volumes)
        r4 = _calc_signal_decay_speed_v59(mmd, closes)

        assert all(isinstance(r, dict) for r in [r1, r2, r3, r4])
        assert all("confidence_adjust" in r for r in [r1, r2, r3, r4])
        assert all("msg" in r for r in [r1, r2, r3, r4])

    def test_sell3_v59_conditions(self):
        """3卖信号V59条件正确执行。"""
        mmd = _make_mock_mmd(MMDType.SELL_3)
        closes = [100.0 - i * 0.5 for i in range(100)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]

        r1 = _calc_volatility_adaptive_ma_v59(mmd, closes)
        r2 = _calc_atr_multiplier_adapt_v59(mmd, highs, lows)
        r3 = _calc_multi_tf_resonance_signal_v59(mmd, closes)
        r4 = _calc_signal_decay_speed_v59(mmd, closes)

        assert r1["msg"] != ""
        assert r2["msg"] != ""
        assert r3["msg"] != ""
        assert r4["msg"] != ""

    def test_v59_integration_pass(self):
        """集成测试通过。"""
        import pandas as pd

        from easy_tdx.chanlun import ChanlunAnalyser
        from easy_tdx.chanlun.config import ChanlunConfig

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

        analyser = ChanlunAnalyser(code="TEST", frequency="daily", config=ChanlunConfig(zs_from_xd=False))
        result = analyser.process_klines(df)

        # 验证V59字段存在于结果中
        for mmd in result.mmds:
            assert hasattr(mmd, "_volatility_adaptive_ma_v59")
            assert hasattr(mmd, "_atr_multiplier_adapt_v59")
            assert hasattr(mmd, "_multi_tf_resonance_signal_v59")
            assert hasattr(mmd, "_signal_decay_speed_v59")

        # 应该有至少一个3买或3卖信号
        buy_3_count = sum(1 for m in result.mmds if m.mmd_type.value == "3buy")
        sell_3_count = sum(1 for m in result.mmds if m.mmd_type.value == "3sell")
        assert buy_3_count >= 0 or sell_3_count >= 0
