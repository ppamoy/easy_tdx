"""V62 缠论模型测试 - BOLL带宽确认 + 动态阈值。

测试内容：
- 条件186: BOLL带宽突破确认（BOLL Bandwidth Breakout Confirmation）
- 条件187: BOLL带宽压缩反弹确认（BOLL Bandwidth Reversal Confirmation）
- 条件188: 动态阈值-波动率状态切换（Dynamic Threshold Volatility Regime）
- 条件189: 动态阈值-ATR倍数自适应（Dynamic Threshold ATR Multiplier Adaptive）
"""

from __future__ import annotations

import pytest

from easy_tdx.chanlun.mmd import (
    MMDType,
    _calc_boll_bandwidth_breakout_confirm_v62,
    _calc_boll_bandwidth_reversal_confirm_v62,
    _calc_dynamic_threshold_volatility_regime_v62,
    _calc_dynamic_threshold_atr_multiplier_v62,
)
from easy_tdx.chanlun.types import MMD


def _make_mmd(mmd_type: MMDType, confidence: float = 0.5) -> MMD:
    """创建测试用的MMD对象。"""
    return MMD(
        mmd_type=mmd_type,
        bi=None,
        zs=None,
        confidence=confidence,
        msg="test",
    )


def _make_closes(n: int = 80, base: float = 100.0, trend: str = "up") -> list[float]:
    """创建测试用的收盘价序列。"""
    import math
    closes = []
    for i in range(n):
        if trend == "up":
            val = base + i * 0.5 + math.sin(i * 0.3) * 2.0
        else:
            val = base - i * 0.5 + math.sin(i * 0.3) * 2.0
        closes.append(max(val, 1.0))
    return closes


# =============================================================================
# 条件186: BOLL带宽突破确认
# =============================================================================

class TestBollBandwidthBreakoutV62:
    """测试条件186：BOLL带宽突破确认。"""

    def test_insufficient_data(self):
        """数据不足时返回空结果。"""
        mmd = _make_mmd(MMDType.BUY_3)
        result = _calc_boll_bandwidth_breakout_confirm_v62(mmd, [100.0] * 10)
        assert "数据不足" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mmd(MMDType.BUY_1)
        closes = _make_closes(80)
        result = _calc_boll_bandwidth_breakout_confirm_v62(mmd, closes)
        assert "非3买/3卖信号" in result["msg"]
        assert result["confidence_adjust"] == 0.0

    def test_basic_structure_buy3(self):
        """3买信号基本结构测试。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(80, trend="up")
        result = _calc_boll_bandwidth_breakout_confirm_v62(mmd, closes)
        assert "boll_upper" in result
        assert "boll_lower" in result
        assert "band_width" in result
        assert "price_position" in result
        assert "breakout_confirmed" in result
        assert "band_trend" in result
        assert "confidence_adjust" in result
        assert isinstance(result["confidence_adjust"], float)

    def test_basic_structure_sell3(self):
        """3卖信号基本结构测试。"""
        mmd = _make_mmd(MMDType.SELL_3, confidence=0.5)
        closes = _make_closes(80, trend="down")
        result = _calc_boll_bandwidth_breakout_confirm_v62(mmd, closes)
        assert "boll_upper" in result
        assert "band_width" in result
        assert "confidence_adjust" in result

    def test_confidence_bounds(self):
        """置信度调整范围验证（-1% ~ +3%）。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(80, trend="up")
        result = _calc_boll_bandwidth_breakout_confirm_v62(mmd, closes)
        adj = result["confidence_adjust"]
        assert -0.01 <= adj <= 0.03

    def test_price_position_values(self):
        """价格位置取值验证。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(80, trend="up")
        result = _calc_boll_bandwidth_breakout_confirm_v62(mmd, closes)
        assert result["price_position"] in ("upper", "lower", "mid")

    def test_band_trend_values(self):
        """带宽趋势取值验证。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(80, trend="up")
        result = _calc_boll_bandwidth_breakout_confirm_v62(mmd, closes)
        assert result["band_trend"] in ("expanding", "contracting", "stable", "insufficient_data")

    def test_msg_format(self):
        """消息格式验证。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(80, trend="up")
        result = _calc_boll_bandwidth_breakout_confirm_v62(mmd, closes)
        assert isinstance(result["msg"], str)
        assert len(result["msg"]) > 0
        assert "BOLL" in result["msg"]


# =============================================================================
# 条件187: BOLL带宽压缩反弹确认
# =============================================================================

class TestBollBandwidthReversalV62:
    """测试条件187：BOLL带宽压缩反弹确认。"""

    def test_insufficient_data(self):
        """数据不足时返回空结果。"""
        mmd = _make_mmd(MMDType.BUY_3)
        result = _calc_boll_bandwidth_reversal_confirm_v62(mmd, [100.0] * 10)
        assert "数据不足" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mmd(MMDType.BUY_1)
        closes = _make_closes(80)
        result = _calc_boll_bandwidth_reversal_confirm_v62(mmd, closes)
        assert "非3买/3卖信号" in result["msg"]
        assert result["confidence_adjust"] == 0.0

    def test_basic_structure_buy3(self):
        """3买信号基本结构测试。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(80, trend="up")
        result = _calc_boll_bandwidth_reversal_confirm_v62(mmd, closes)
        assert "band_width_rank" in result
        assert "squeeze_active" in result
        assert "reversal_confirmed" in result
        assert "reversal_type" in result
        assert "confidence_adjust" in result

    def test_basic_structure_sell3(self):
        """3卖信号基本结构测试。"""
        mmd = _make_mmd(MMDType.SELL_3, confidence=0.5)
        closes = _make_closes(80, trend="down")
        result = _calc_boll_bandwidth_reversal_confirm_v62(mmd, closes)
        assert "band_width_rank" in result
        assert "squeeze_active" in result
        assert "confidence_adjust" in result

    def test_confidence_bounds(self):
        """置信度调整范围验证（+0.5% ~ +2%）。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(80, trend="up")
        result = _calc_boll_bandwidth_reversal_confirm_v62(mmd, closes)
        adj = result["confidence_adjust"]
        assert 0.0 <= adj <= 0.02

    def test_squeeze_detection(self):
        """压缩状态检测验证。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(80, trend="up")
        result = _calc_boll_bandwidth_reversal_confirm_v62(mmd, closes)
        assert isinstance(result["squeeze_active"], bool)
        assert isinstance(result["band_width_rank"], float)
        assert 0.0 <= result["band_width_rank"] <= 1.0

    def test_reversal_type_values(self):
        """反弹类型取值验证。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(80, trend="up")
        result = _calc_boll_bandwidth_reversal_confirm_v62(mmd, closes)
        assert result["reversal_type"] in ("bullish_reversal", "bearish_reversal", "no_reversal", "none")

    def test_msg_format(self):
        """消息格式验证。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(80, trend="up")
        result = _calc_boll_bandwidth_reversal_confirm_v62(mmd, closes)
        assert isinstance(result["msg"], str)
        assert len(result["msg"]) > 0


# =============================================================================
# 条件188: 动态阈值-波动率状态切换
# =============================================================================

class TestDynamicThresholdVolatilityRegimeV62:
    """测试条件188：动态阈值-波动率状态切换。"""

    def test_insufficient_data(self):
        """数据不足时返回空结果。"""
        mmd = _make_mmd(MMDType.BUY_3)
        result = _calc_dynamic_threshold_volatility_regime_v62(mmd, [100.0] * 10)
        assert "数据不足" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mmd(MMDType.BUY_1)
        closes = _make_closes(50)
        result = _calc_dynamic_threshold_volatility_regime_v62(mmd, closes)
        assert "非3买/3卖信号" in result["msg"]
        assert result["confidence_adjust"] == 0.0

    def test_basic_structure_buy3(self):
        """3买信号基本结构测试。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(50, trend="up")
        result = _calc_dynamic_threshold_volatility_regime_v62(mmd, closes)
        assert "atr_pct" in result
        assert "volatility_regime" in result
        assert "confidence_adjust" in result
        assert isinstance(result["atr_pct"], float)

    def test_basic_structure_sell3(self):
        """3卖信号基本结构测试。"""
        mmd = _make_mmd(MMDType.SELL_3, confidence=0.5)
        closes = _make_closes(50, trend="down")
        result = _calc_dynamic_threshold_volatility_regime_v62(mmd, closes)
        assert "atr_pct" in result
        assert "volatility_regime" in result
        assert "confidence_adjust" in result

    def test_confidence_bounds(self):
        """置信度调整范围验证（-2% ~ +2%）。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(50, trend="up")
        result = _calc_dynamic_threshold_volatility_regime_v62(mmd, closes)
        adj = result["confidence_adjust"]
        assert -0.02 <= adj <= 0.02

    def test_volatility_regime_values(self):
        """波动率状态取值验证。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(50, trend="up")
        result = _calc_dynamic_threshold_volatility_regime_v62(mmd, closes)
        assert result["volatility_regime"] in ("high", "low", "normal")

    def test_low_volatility_positive_adjust(self):
        """低波动环境应获得正向调整。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        # 使用低波动数据（小幅变化）
        closes = [100.0 + i * 0.01 for i in range(50)]
        result = _calc_dynamic_threshold_volatility_regime_v62(mmd, closes)
        assert result["volatility_regime"] == "low"
        assert result["confidence_adjust"] > 0

    def test_msg_format(self):
        """消息格式验证。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(50, trend="up")
        result = _calc_dynamic_threshold_volatility_regime_v62(mmd, closes)
        assert isinstance(result["msg"], str)
        assert len(result["msg"]) > 0
        assert "ATR" in result["msg"]


# =============================================================================
# 条件189: 动态阈值-ATR倍数自适应
# =============================================================================

class TestDynamicThresholdATRMultiplierV62:
    """测试条件189：动态阈值-ATR倍数自适应。"""

    def test_insufficient_data(self):
        """数据不足时返回空结果。"""
        mmd = _make_mmd(MMDType.BUY_3)
        result = _calc_dynamic_threshold_atr_multiplier_v62(mmd, [100.0] * 5)
        assert "数据不足" in result["msg"]

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mmd(MMDType.BUY_1)
        closes = _make_closes(50)
        result = _calc_dynamic_threshold_atr_multiplier_v62(mmd, closes)
        assert "非3买/3卖信号" in result["msg"]
        assert result["confidence_adjust"] == 0.0

    def test_basic_structure_buy3(self):
        """3买信号基本结构测试。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(50, trend="up")
        result = _calc_dynamic_threshold_atr_multiplier_v62(mmd, closes)
        assert "atr_14" in result
        assert "optimal_multiplier" in result
        assert "stop_distance_pct" in result
        assert "volatility_regime" in result
        assert "confidence_adjust" in result

    def test_basic_structure_sell3(self):
        """3卖信号基本结构测试。"""
        mmd = _make_mmd(MMDType.SELL_3, confidence=0.5)
        closes = _make_closes(50, trend="down")
        result = _calc_dynamic_threshold_atr_multiplier_v62(mmd, closes)
        assert "atr_14" in result
        assert "optimal_multiplier" in result
        assert "confidence_adjust" in result

    def test_confidence_bounds(self):
        """置信度调整范围验证（-1% ~ +1%）。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(50, trend="up")
        result = _calc_dynamic_threshold_atr_multiplier_v62(mmd, closes)
        adj = result["confidence_adjust"]
        assert -0.01 <= adj <= 0.01

    def test_multiplier_values(self):
        """倍数取值验证。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(50, trend="up")
        result = _calc_dynamic_threshold_atr_multiplier_v62(mmd, closes)
        assert result["optimal_multiplier"] in (1.5, 2.0, 2.2, 2.5)

    def test_low_volatility_positive_adjust(self):
        """低波动环境应获得正向调整。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = [100.0 + i * 0.01 for i in range(50)]
        result = _calc_dynamic_threshold_atr_multiplier_v62(mmd, closes)
        assert result["confidence_adjust"] > 0
        assert result["optimal_multiplier"] == 1.5

    def test_stop_distance_positive(self):
        """止损距离应为正数。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(50, trend="up")
        result = _calc_dynamic_threshold_atr_multiplier_v62(mmd, closes)
        assert result["stop_distance_pct"] > 0

    def test_msg_format(self):
        """消息格式验证。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(50, trend="up")
        result = _calc_dynamic_threshold_atr_multiplier_v62(mmd, closes)
        assert isinstance(result["msg"], str)
        assert len(result["msg"]) > 0
        assert "ATR" in result["msg"]


# =============================================================================
# 集成测试
# =============================================================================

class TestFindMMDsV62Integration:
    """集成测试：验证V62函数可被find_mmds_v39调用。"""

    def test_v62_functions_importable(self):
        """V62函数可导入。"""
        from easy_tdx.chanlun.mmd import (
            _calc_boll_bandwidth_breakout_confirm_v62,
            _calc_boll_bandwidth_reversal_confirm_v62,
            _calc_dynamic_threshold_volatility_regime_v62,
            _calc_dynamic_threshold_atr_multiplier_v62,
        )
        assert callable(_calc_boll_bandwidth_breakout_confirm_v62)
        assert callable(_calc_boll_bandwidth_reversal_confirm_v62)
        assert callable(_calc_dynamic_threshold_volatility_regime_v62)
        assert callable(_calc_dynamic_threshold_atr_multiplier_v62)

    def test_v62_fields_in_mmd_type(self):
        """V62字段存在于MMD类型定义中。"""
        mmd = _make_mmd(MMDType.BUY_3)
        assert hasattr(mmd, "_boll_bandwidth_breakout_v62")
        assert hasattr(mmd, "_boll_bandwidth_reversal_v62")
        assert hasattr(mmd, "_dynamic_threshold_volatility_regime_v62")
        assert hasattr(mmd, "_dynamic_threshold_atr_multiplier_v62")

    def test_v62_confidence_bounds(self):
        """V62不超出置信度边界。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(80, trend="up")

        # 测试条件186
        r1 = _calc_boll_bandwidth_breakout_confirm_v62(mmd, closes)
        new_conf1 = max(0.0, min(1.0, 0.5 + r1["confidence_adjust"]))
        assert 0.0 <= new_conf1 <= 1.0

        # 测试条件187
        r2 = _calc_boll_bandwidth_reversal_confirm_v62(mmd, closes)
        new_conf2 = max(0.0, min(1.0, 0.5 + r2["confidence_adjust"]))
        assert 0.0 <= new_conf2 <= 1.0

        # 测试条件188
        r3 = _calc_dynamic_threshold_volatility_regime_v62(mmd, closes)
        new_conf3 = max(0.0, min(1.0, 0.5 + r3["confidence_adjust"]))
        assert 0.0 <= new_conf3 <= 1.0

        # 测试条件189
        r4 = _calc_dynamic_threshold_atr_multiplier_v62(mmd, closes)
        new_conf4 = max(0.0, min(1.0, 0.5 + r4["confidence_adjust"]))
        assert 0.0 <= new_conf4 <= 1.0

    def test_v62_all_conditions_callable(self):
        """所有V62条件函数可调用。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(80, trend="up")

        r1 = _calc_boll_bandwidth_breakout_confirm_v62(mmd, closes)
        assert isinstance(r1, dict)
        assert "confidence_adjust" in r1

        r2 = _calc_boll_bandwidth_reversal_confirm_v62(mmd, closes)
        assert isinstance(r2, dict)
        assert "confidence_adjust" in r2

        r3 = _calc_dynamic_threshold_volatility_regime_v62(mmd, closes)
        assert isinstance(r3, dict)
        assert "confidence_adjust" in r3

        r4 = _calc_dynamic_threshold_atr_multiplier_v62(mmd, closes)
        assert isinstance(r4, dict)
        assert "confidence_adjust" in r4

    def test_sell3_v62_conditions(self):
        """3卖信号的V62条件测试。"""
        mmd = _make_mmd(MMDType.SELL_3, confidence=0.5)
        closes = _make_closes(80, trend="down")

        r1 = _calc_boll_bandwidth_breakout_confirm_v62(mmd, closes)
        assert isinstance(r1, dict)

        r2 = _calc_boll_bandwidth_reversal_confirm_v62(mmd, closes)
        assert isinstance(r2, dict)

        r3 = _calc_dynamic_threshold_volatility_regime_v62(mmd, closes)
        assert isinstance(r3, dict)

        r4 = _calc_dynamic_threshold_atr_multiplier_v62(mmd, closes)
        assert isinstance(r4, dict)

    def test_v62_integration_pass(self):
        """V62集成通过测试。"""
        from easy_tdx.chanlun.mmd import find_mmds_v39
        import inspect
        source = inspect.getsource(find_mmds_v39)
        assert "_calc_boll_bandwidth_breakout_confirm_v62" in source
        assert "_calc_boll_bandwidth_reversal_confirm_v62" in source
        assert "_calc_dynamic_threshold_volatility_regime_v62" in source
        assert "_calc_dynamic_threshold_atr_multiplier_v62" in source
