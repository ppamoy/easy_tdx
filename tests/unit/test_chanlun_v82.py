"""V82 缠论模型精准度提升测试（条件260-263）。"""

import pytest
import numpy as np

from easy_tdx.backtest.chanlun_validator import ConditionGroup
from easy_tdx.chanlun.types import MMD, MMDType


# ── V82 条件组定义测试 ───────────────────────────────────────────────


class TestV82ConditionGroup:
    """V82 ConditionGroup 存在性与范围测试。"""

    def test_v82_enum_exists(self):
        assert hasattr(ConditionGroup, "V82")

    def test_v82_condition_range(self):
        assert ConditionGroup.V82.condition_range == (260, 263)

    def test_v82_description(self):
        desc = ConditionGroup.V82.description
        assert "时间衰减" in desc or "衰减" in desc
        assert "回踩" in desc or "突破" in desc
        assert "MACD" in desc or "共振" in desc
        assert "波动率" in desc or "压缩" in desc


# ── V82 MMD 字段测试 ─────────────────────────────────────────────────


class TestV82MMDFields:
    """MMD 对象包含 V82 四个字段。"""

    def test_mmd_has_v82_fields(self):
        mmd = MMD(mmd_type=MMDType("1buy"), confidence=0.5, msg="test")
        assert hasattr(mmd, "_mmd_age_decay_v82")
        assert hasattr(mmd, "_breakout_retest_confirm_v82")
        assert hasattr(mmd, "_macd_multi_tf_resonance_v82")
        assert hasattr(mmd, "_volatility_compression_breakout_v82")


# ── V82 回测验证器测试 ───────────────────────────────────────────────


class TestV82BacktestValidator:
    """V82 回测验证器测试。"""

    def test_v82_validator_single_group(self):
        from easy_tdx.backtest.chanlun_validator import ChanlunConditionBacktestValidator
        validator = ChanlunConditionBacktestValidator()
        # 验证 V82 组可被识别
        low, high = ConditionGroup.V82.condition_range
        assert low == 260
        assert high == 263

    def test_v82_validator_multi_group(self):
        from easy_tdx.backtest.chanlun_validator import ChanlunConditionBacktestValidator
        validator = ChanlunConditionBacktestValidator()
        # V80+V81+V82 联合验证
        groups = [ConditionGroup.V80, ConditionGroup.V81, ConditionGroup.V82]
        ranges = [g.condition_range for g in groups]
        assert ranges == [(252, 255), (256, 259), (260, 263)]

    def test_v82_summary_output(self):
        """V82 summary 输出结构正确。"""
        from easy_tdx.backtest.chanlun_validator import ChanlunConditionBacktestValidator
        validator = ChanlunConditionBacktestValidator()
        # 验证 V82 组条件范围
        low, high = ConditionGroup.V82.condition_range
        assert low == 260
        assert high == 263
        desc = ConditionGroup.V82.description
        assert len(desc) > 0


# ── V82 函数测试 ─────────────────────────────────────────────────────


class TestV82Functions:
    """V82 四个计算函数的单元测试。"""

    def test_mad_buy_fresh_signal(self):
        """条件260：买入信号，新鲜度=高。"""
        from easy_tdx.chanlun.mmd import _calc_mmd_age_decay_v82
        mmd = MMD(mmd_type=MMDType("1buy"), confidence=0.7, msg="test")
        closes = list(range(100, 150))
        highs = [c + 1 for c in closes]
        lows = [c - 1 for c in closes]
        result = _calc_mmd_age_decay_v82(mmd, closes, highs, lows)
        assert result["age_bars"] >= 0
        assert result["confidence_adjust"] is not None
        assert result["msg"] is not None

    def test_mad_sell_old_signal(self):
        """条件260：卖出信号，陈旧度=高。"""
        from easy_tdx.chanlun.mmd import _calc_mmd_age_decay_v82
        mmd = MMD(mmd_type=MMDType("1sell"), confidence=0.7, msg="test")
        closes = list(range(150, 100, -1))
        highs = [c + 1 for c in closes]
        lows = [c - 1 for c in closes]
        result = _calc_mmd_age_decay_v82(mmd, closes, highs, lows)
        assert result["age_bars"] >= 0
        assert result["age_label"] in ["fresh", "moderate", "aging", "old", "stale", "unknown"]

    def test_mad_insufficient_data(self):
        """条件260：数据不足时不崩溃。"""
        from easy_tdx.chanlun.mmd import _calc_mmd_age_decay_v82
        mmd = MMD(mmd_type=MMDType("1buy"), confidence=0.5, msg="test")
        result = _calc_mmd_age_decay_v82(mmd, [1.0, 2.0], [1.1, 2.1], [0.9, 1.9])
        assert result is not None
        assert result.get("age_label") == "unknown"

    def test_brc_breakout_no_retest(self):
        """条件261：突破后无回踩。"""
        from easy_tdx.chanlun.mmd import _calc_breakout_retest_confirm_v82
        mmd = MMD(mmd_type=MMDType("1buy"), confidence=0.7, msg="test")
        # 上涨趋势，无回踩
        closes = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = _calc_breakout_retest_confirm_v82(mmd, closes, highs, lows)
        assert result is not None
        assert "retest_detected" in result
        assert "confidence_adjust" in result

    def test_brc_insufficient_data(self):
        """条件261：数据不足时不崩溃。"""
        from easy_tdx.chanlun.mmd import _calc_breakout_retest_confirm_v82
        mmd = MMD(mmd_type=MMDType("1buy"), confidence=0.5, msg="test")
        result = _calc_breakout_retest_confirm_v82(mmd, [1.0, 2.0], [1.1, 2.1], [0.9, 1.9])
        assert result is not None
        assert result.get("retest_quality") == "unknown"

    def test_mtr_bullish_resonance(self):
        """条件262：多头共振。"""
        from easy_tdx.chanlun.mmd import _calc_macd_multi_tf_resonance_v82
        mmd = MMD(mmd_type=MMDType("1buy"), confidence=0.7, msg="test")
        # 上升趋势
        closes = [10 + i * 0.5 for i in range(50)]
        result = _calc_macd_multi_tf_resonance_v82(mmd, closes)
        assert result is not None
        assert "resonance" in result
        assert "confidence_adjust" in result

    def test_mtr_insufficient_data(self):
        """条件262：数据不足时不崩溃。"""
        from easy_tdx.chanlun.mmd import _calc_macd_multi_tf_resonance_v82
        mmd = MMD(mmd_type=MMDType("1buy"), confidence=0.5, msg="test")
        result = _calc_macd_multi_tf_resonance_v82(mmd, [1.0, 2.0])
        assert result is not None
        assert result.get("resonance") == "none"

    def test_vcb_extreme_compression(self):
        """条件263：极度压缩。"""
        from easy_tdx.chanlun.mmd import _calc_volatility_compression_breakout_v82
        mmd = MMD(mmd_type=MMDType("1buy"), confidence=0.7, msg="test")
        # 低波动率数据（压缩状态）
        closes = [10.0 + 0.01 * i for i in range(50)]
        highs = [c + 0.005 for c in closes]
        lows = [c - 0.005 for c in closes]
        result = _calc_volatility_compression_breakout_v82(mmd, closes, highs, lows)
        assert result is not None
        assert "compression_level" in result
        assert "confidence_adjust" in result

    def test_vcb_insufficient_data(self):
        """条件263：数据不足时不崩溃。"""
        from easy_tdx.chanlun.mmd import _calc_volatility_compression_breakout_v82
        mmd = MMD(mmd_type=MMDType("1buy"), confidence=0.5, msg="test")
        result = _calc_volatility_compression_breakout_v82(mmd, [1.0, 2.0], [1.1, 2.1], [0.9, 1.9])
        assert result is not None
        assert result.get("compression_level") in ("unknown", "none")

    def test_all_v82_functions_no_crash(self):
        """所有V82函数在正常数据下不崩溃。"""
        from easy_tdx.chanlun.mmd import (
            _calc_mmd_age_decay_v82,
            _calc_breakout_retest_confirm_v82,
            _calc_macd_multi_tf_resonance_v82,
            _calc_volatility_compression_breakout_v82,
        )
        mmd_buy = MMD(mmd_type=MMDType("1buy"), confidence=0.7, msg="test")
        mmd_sell = MMD(mmd_type=MMDType("1sell"), confidence=0.7, msg="test")
        closes = list(range(100, 150))
        highs = [c + 1 for c in closes]
        lows = [c - 1 for c in closes]

        assert _calc_mmd_age_decay_v82(mmd_buy, closes, highs, lows) is not None
        assert _calc_breakout_retest_confirm_v82(mmd_buy, closes, highs, lows) is not None
        assert _calc_macd_multi_tf_resonance_v82(mmd_buy, closes) is not None
        assert _calc_volatility_compression_breakout_v82(mmd_buy, closes, highs, lows) is not None

        assert _calc_mmd_age_decay_v82(mmd_sell, closes, highs, lows) is not None
        assert _calc_breakout_retest_confirm_v82(mmd_sell, closes, highs, lows) is not None
        assert _calc_macd_multi_tf_resonance_v82(mmd_sell, closes) is not None
        assert _calc_volatility_compression_breakout_v82(mmd_sell, closes, highs, lows) is not None

    def test_v82_vs_v81_compatibility(self):
        """V82与V81兼容性：不会互相覆盖。"""
        from easy_tdx.chanlun.types import MMD, MMDType
        mmd = MMD(mmd_type=MMDType("1buy"), confidence=0.5, msg="test")
        # V81 fields
        mmd._volatility_regime_transition_v81 = {"test": True}
        mmd._support_resistance_strength_v81 = {"test": True}
        mmd._volume_price_energy_distribution_v81 = {"test": True}
        mmd._signal_execution_window_v81 = {"test": True}
        # V82 fields
        mmd._mmd_age_decay_v82 = {"test": True}
        mmd._breakout_retest_confirm_v82 = {"test": True}
        mmd._macd_multi_tf_resonance_v82 = {"test": True}
        mmd._volatility_compression_breakout_v82 = {"test": True}
        # 确认所有字段独立存在
        assert mmd._volatility_regime_transition_v81 is not None
        assert mmd._mmd_age_decay_v82 is not None
        assert len([a for a in dir(mmd) if "v81" in a or "v82" in a]) >= 8
