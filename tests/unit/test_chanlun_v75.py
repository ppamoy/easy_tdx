"""
V75 缠论条件测试 — 条件232-235
回调深度验证 + 中枢回踩确认 + 量峰持续评分 + 多信号时间一致性
"""

import pytest
import numpy as np
from easy_tdx.backtest.chanlun_validator import ConditionGroup, ChanlunConditionBacktestValidator
from easy_tdx.chanlun.types import MMD, MMDType, ZS


# ──────────────────────────────────────────────────────────────────────────────
# 测试数据辅助
# ──────────────────────────────────────────────────────────────────────────────

def _make_trending_df(n: int = 100, trend: str = "up"):
    """生成趋势K线数据用于测试。"""
    np.random.seed(123)
    closes = [100.0]
    for _ in range(n):
        drift = 0.001 if trend == "up" else -0.001
        c = closes[-1] * (1 + drift + np.random.randn() * 0.015)
        closes.append(max(c, 1.0))
    highs = [c + abs(np.random.randn()) * 0.5 for c in closes]
    lows = [c - abs(np.random.randn()) * 0.5 for c in closes]
    volumes = [1e6 * (1 + abs(np.random.randn()) * 0.3) for _ in range(n + 1)]
    return closes, highs, lows, volumes


def _make_df(closes, highs, lows, volumes):
    import pandas as pd
    return pd.DataFrame({
        "close": closes,
        "high": highs,
        "low": lows,
        "volume": volumes,
    })


# ──────────────────────────────────────────────────────────────────────────────
# V75 ConditionGroup 枚举测试
# ──────────────────────────────────────────────────────────────────────────────

class TestV75ConditionGroup:
    """V75 ConditionGroup 枚举测试。"""

    def test_v75_group_exists(self):
        assert hasattr(ConditionGroup, 'V75')
        assert ConditionGroup.V75.value == "v75"

    def test_v75_condition_range(self):
        group = ConditionGroup.V75
        start, end = group.condition_range
        assert start == 232
        assert end == 235

    def test_v75_description(self):
        desc = ConditionGroup.V75.description
        assert any(kw in desc for kw in ["回调", "中枢回踩", "量峰", "时间一致"])


# ──────────────────────────────────────────────────────────────────────────────
# V75 MMD 增强字段存在性测试
# ──────────────────────────────────────────────────────────────────────────────

class TestV75MMDFields:
    """V75 MMD 增强字段存在性测试。"""

    def test_v75_fields_exist_on_mmd(self):
        from easy_tdx.chanlun.types import MMD
        mmd = MMD(mmd_type="buy_3", confidence=0.5, bi=None)
        assert hasattr(mmd, "_pullback_depth_validation_v75")
        assert hasattr(mmd, "_zhongshu_retracement_confirm_v75")
        assert hasattr(mmd, "_volume_peak_duration_v75")
        assert hasattr(mmd, "_multi_signal_time_consistency_v75")


# ──────────────────────────────────────────────────────────────────────────────
# V75 回测验证器测试
# ──────────────────────────────────────────────────────────────────────────────

class TestV75BacktestValidator:
    """V75 回测验证器测试。"""

    def test_v75_validator_usage(self):
        validator = ChanlunConditionBacktestValidator(min_bars=150)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V75])
        assert len(results) >= 1
        assert results[0].group == ConditionGroup.V75

    def test_v75_multi_group_validation(self):
        validator = ChanlunConditionBacktestValidator(min_bars=150)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V74, ConditionGroup.V75])
        groups = {r.group for r in results}
        assert groups == {ConditionGroup.V74, ConditionGroup.V75}

    def test_v75_summary_output(self):
        validator = ChanlunConditionBacktestValidator(min_bars=150)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V75])
        summary = results[0].summary()
        assert "V75" in summary
        assert "回调" in summary or "232" in summary


# ──────────────────────────────────────────────────────────────────────────────
# V75 计算函数功能测试
# ──────────────────────────────────────────────────────────────────────────────

class TestV75Functions:
    """V75 计算函数功能测试。"""

    def test_pullback_depth_validation(self):
        """回调深度验证应返回正确结构。"""
        from easy_tdx.chanlun.mmd import _calc_pullback_depth_validation_v75
        from easy_tdx.chanlun.types import MMD, MMDType
        np.random.seed(88)
        closes = [100.0]
        highs = [100.5]
        lows = [99.5]
        for _ in range(80):
            c = closes[-1] * (1 + np.random.randn() * 0.012)
            h = max(c, closes[-1]) * (1 + abs(np.random.randn()) * 0.005)
            l = min(c, closes[-1]) * (1 - abs(np.random.randn()) * 0.005)
            closes.append(c)
            highs.append(h)
            lows.append(l)
        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, bi=None)
        result = _calc_pullback_depth_validation_v75(mmd, closes, highs, lows)
        assert "pullback_depth" in result
        assert "max_retracement" in result
        assert "fibonacci_level" in result
        assert "confirm_signal" in result
        assert "confidence_adjust" in result
        assert "msg" in result
        assert result["fibonacci_level"] in (
            "shallow_15", "fib_236", "fib_382", "fib_50", "deep_over_50", "none"
        )

    def test_pullback_depth_validation_sell(self):
        """卖出信号时回调深度验证逻辑正确。"""
        from easy_tdx.chanlun.mmd import _calc_pullback_depth_validation_v75
        from easy_tdx.chanlun.types import MMD, MMDType
        np.random.seed(89)
        closes = [100.0]
        highs = [100.5]
        lows = [99.5]
        for _ in range(80):
            c = closes[-1] * (1 + np.random.randn() * 0.01)
            h = max(c, closes[-1]) * (1 + abs(np.random.randn()) * 0.005)
            l = min(c, closes[-1]) * (1 - abs(np.random.randn()) * 0.005)
            closes.append(c)
            highs.append(h)
            lows.append(l)
        mmd_sell = MMD(mmd_type=MMDType.SELL_3, confidence=0.5, bi=None)
        result = _calc_pullback_depth_validation_v75(mmd_sell, closes, highs, lows)
        assert "pullback_depth" in result
        assert "fibonacci_level" in result
        assert isinstance(result["confirm_signal"], bool)

    def test_zhongshu_retracement_confirm(self):
        """中枢区间回踩确认应返回正确结构。"""
        from easy_tdx.chanlun.mmd import _calc_zhongshu_retracement_confirm_v75
        from easy_tdx.chanlun.types import MMD, MMDType
        np.random.seed(90)
        closes = [100.0]
        for _ in range(80):
            c = closes[-1] * (1 + np.random.randn() * 0.01)
            closes.append(c)
        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, bi=None)
        zss = [
            ZS(zg=108.0, zd=92.0, index=0),
            ZS(zg=105.0, zd=88.0, index=1),
            ZS(zg=103.0, zd=85.0, index=2),
        ]
        result = _calc_zhongshu_retracement_confirm_v75(mmd, zss, closes)
        assert "retracement_type" in result
        assert "nearest_zs_dist" in result
        assert "bounce_strength" in result
        assert "confirm_signal" in result
        assert "confidence_adjust" in result
        assert "msg" in result
        assert result["retracement_type"] in (
            "zs_support_bounce", "above_zs_confirmed", "inside_zs",
            "below_zs", "zs_resistance_bounce", "below_zs_confirmed", "none"
        )

    def test_zhongshu_retracement_no_zs(self):
        """无中枢数据时返回默认值。"""
        from easy_tdx.chanlun.mmd import _calc_zhongshu_retracement_confirm_v75
        from easy_tdx.chanlun.types import MMD, MMDType
        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, bi=None)
        result = _calc_zhongshu_retracement_confirm_v75(mmd, [], [100.0, 101.0])
        assert result["msg"] != ""
        assert result["confirm_signal"] is False

    def test_volume_peak_duration(self):
        """量峰持续时间评分应返回正确结构。"""
        from easy_tdx.chanlun.mmd import _calc_volume_peak_duration_v75
        from easy_tdx.chanlun.types import MMD, MMDType
        np.random.seed(91)
        volumes = [1e6]
        closes = [100.0]
        for _ in range(80):
            c = closes[-1] * (1 + np.random.randn() * 0.01)
            closes.append(c)
            # 在最后20根中增加一些放量
            if _ > 60:
                volumes.append(1e6 * (1.8 + abs(np.random.randn()) * 0.3))
            else:
                volumes.append(1e6 * (1 + abs(np.random.randn()) * 0.3))
        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, bi=None)
        result = _calc_volume_peak_duration_v75(mmd, volumes, closes)
        assert "peak_duration" in result
        assert "avg_vol_ratio" in result
        assert "peak_days" in result
        assert "confirm_signal" in result
        assert "confidence_adjust" in result
        assert "msg" in result
        assert isinstance(result["confirm_signal"], bool)

    def test_volume_peak_duration_buy_vs_sell(self):
        """买入与卖出信号的量峰判断逻辑。"""
        from easy_tdx.chanlun.mmd import _calc_volume_peak_duration_v75
        from easy_tdx.chanlun.types import MMD, MMDType
        np.random.seed(92)
        volumes = [1e6] * 100
        closes = [100.0]
        for _ in range(99):
            c = closes[-1] * (1 + np.random.randn() * 0.01)
            closes.append(c)
        # 均量比约1.0，不满足放量条件
        mmd_buy = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, bi=None)
        result_buy = _calc_volume_peak_duration_v75(mmd_buy, volumes, closes)
        assert "confirm_signal" in result_buy

    def test_multi_signal_time_consistency(self):
        """多信号时间一致性应返回正确结构。"""
        from easy_tdx.chanlun.mmd import _calc_multi_signal_time_consistency_v75
        from easy_tdx.chanlun.types import MMD, MMDType
        np.random.seed(93)
        closes = [100.0]
        highs = [100.5]
        lows = [99.5]
        volumes = [1e6]
        for _ in range(80):
            c = closes[-1] * (1 + np.random.randn() * 0.01)
            h = max(c, closes[-1]) * (1 + abs(np.random.randn()) * 0.005)
            l = min(c, closes[-1]) * (1 - abs(np.random.randn()) * 0.005)
            closes.append(c)
            highs.append(h)
            lows.append(l)
            volumes.append(1e6 * (1 + abs(np.random.randn()) * 0.2))
        macd_data = [{"hist": 0.05} for _ in range(80)]
        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, bi=None)
        result = _calc_multi_signal_time_consistency_v75(
            mmd, closes, highs, lows, macd_data, volumes
        )
        assert "consistency_score" in result
        assert "signal_dates" in result
        assert "alignment_ratio" in result
        assert "confirm_signal" in result
        assert "confidence_adjust" in result
        assert "msg" in result
        assert 0.0 <= result["consistency_score"] <= 1.0

    def test_multi_signal_time_consistency_insufficient(self):
        """数据不足时应返回默认值。"""
        from easy_tdx.chanlun.mmd import _calc_multi_signal_time_consistency_v75
        from easy_tdx.chanlun.types import MMD, MMDType
        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, bi=None)
        short_closes = [100.0, 101.0, 102.0]
        result = _calc_multi_signal_time_consistency_v75(
            mmd, short_closes, None, None, None, None
        )
        assert result["msg"] != ""
        assert result["consistency_score"] == 0.0

    def test_pullback_depth_insufficient_data(self):
        """回调深度验证数据不足时返回默认值。"""
        from easy_tdx.chanlun.mmd import _calc_pullback_depth_validation_v75
        from easy_tdx.chanlun.types import MMD, MMDType
        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, bi=None)
        short_closes = [100.0, 101.0, 102.0]
        result = _calc_pullback_depth_validation_v75(mmd, short_closes, None, None)
        assert result["msg"] != ""

    def test_all_v75_functions_no_crash(self):
        """所有V75函数在正常输入下不应抛出异常。"""
        from easy_tdx.chanlun.mmd import (
            _calc_pullback_depth_validation_v75,
            _calc_zhongshu_retracement_confirm_v75,
            _calc_volume_peak_duration_v75,
            _calc_multi_signal_time_consistency_v75,
        )
        from easy_tdx.chanlun.types import MMD, MMDType, ZS
        np.random.seed(94)
        closes = [100.0]
        highs = [100.5]
        lows = [99.5]
        volumes = [1e6]
        for _ in range(100):
            c = closes[-1] * (1 + np.random.randn() * 0.01)
            h = max(c, closes[-1]) * (1 + abs(np.random.randn()) * 0.005)
            l = min(c, closes[-1]) * (1 - abs(np.random.randn()) * 0.005)
            closes.append(c)
            highs.append(h)
            lows.append(l)
            volumes.append(1e6 * (1 + abs(np.random.randn()) * 0.2))
        macd_data = [{"hist": 0.05} for _ in range(100)]
        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, bi=None)
        zss = [ZS(zg=108.0, zd=92.0, index=i) for i in range(3)]

        r1 = _calc_pullback_depth_validation_v75(mmd, closes, highs, lows)
        assert r1 is not None
        assert r1["pullback_depth"] >= 0.0

        r2 = _calc_zhongshu_retracement_confirm_v75(mmd, zss, closes)
        assert r2 is not None
        assert "retracement_type" in r2

        r3 = _calc_volume_peak_duration_v75(mmd, volumes, closes)
        assert r3 is not None
        assert r3["peak_days"] >= 0

        r4 = _calc_multi_signal_time_consistency_v75(
            mmd, closes, highs, lows, macd_data, volumes
        )
        assert r4 is not None
        assert 0.0 <= r4["consistency_score"] <= 1.0
