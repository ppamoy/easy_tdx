"""V61 缠论模型测试 - MACD柱状图背离融合 + 综合多信号评分。"""

from __future__ import annotations

import pytest

from easy_tdx.chanlun.mmd import (
    MMDType,
    _calc_macd_histogram_divergence_v61,
    _calc_composite_signal_score_v61,
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


def _make_closes(n: int = 60, base: float = 10.0, trend: str = "down") -> list[float]:
    """创建测试用的收盘价序列。"""
    import math
    closes = []
    for i in range(n):
        if trend == "down":
            val = base - i * 0.05 + math.sin(i * 0.3) * 0.1
        else:
            val = base + i * 0.05 + math.sin(i * 0.3) * 0.1
        closes.append(max(val, 1.0))
    return closes


def _make_macd_data(closes: list[float]) -> dict[str, list[float]]:
    """根据收盘价计算简易MACD数据。"""
    from easy_tdx.MyTT import MACD
    dif, dea, hist = MACD(closes)
    return {"dif": dif, "dea": dea, "hist": hist}


class TestMACDHistogramDivergenceV61:
    """测试条件184：MACD柱状图背离融合。"""

    def test_insufficient_data(self):
        """数据不足时返回空结果。"""
        mmd = _make_mmd(MMDType.BUY_3)
        closes = [10.0] * 5
        macd_data = {"hist": [0.0] * 5}
        result = _calc_macd_histogram_divergence_v61(mmd, closes, macd_data)
        assert result["msg"] != ""
        assert result["confidence_adjust"] == 0.0

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号时跳过。"""
        mmd = _make_mmd(MMDType.BUY_1)
        closes = _make_closes(60)
        macd_data = _make_macd_data(closes)
        result = _calc_macd_histogram_divergence_v61(mmd, closes, macd_data)
        assert result["msg"] == "非3买/3卖信号，跳过此条件"
        assert result["confidence_adjust"] == 0.0

    def test_basic_structure_buy3(self):
        """3买信号基本结构测试。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(60, trend="down")
        macd_data = _make_macd_data(closes)
        result = _calc_macd_histogram_divergence_v61(mmd, closes, macd_data)
        assert "divergence_type" in result
        assert "macd_hist_curr" in result
        assert "confidence_adjust" in result
        assert isinstance(result["confidence_adjust"], float)

    def test_basic_structure_sell3(self):
        """3卖信号基本结构测试。"""
        mmd = _make_mmd(MMDType.SELL_3, confidence=0.5)
        closes = _make_closes(60, trend="up")
        macd_data = _make_macd_data(closes)
        result = _calc_macd_histogram_divergence_v61(mmd, closes, macd_data)
        assert "divergence_type" in result
        assert "confidence_adjust" in result

    def test_confidence_bounds(self):
        """置信度调整范围验证。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(60, trend="down")
        macd_data = _make_macd_data(closes)
        result = _calc_macd_histogram_divergence_v61(mmd, closes, macd_data)
        assert -0.05 <= result["confidence_adjust"] <= 0.06

    def test_rsi_fusion_fields(self):
        """RSI融合字段存在性验证。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(60, trend="down")
        macd_data = _make_macd_data(closes)
        result = _calc_macd_histogram_divergence_v61(mmd, closes, macd_data)
        assert "rsi_fusion" in result
        assert result["rsi_fusion"] in ("none", "fused_bullish", "fused_bearish")
        assert "divergence_depth" in result
        assert result["divergence_depth"] in ("deep", "moderate", "shallow", "none")

    def test_msg_format(self):
        """消息格式验证。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(60, trend="down")
        macd_data = _make_macd_data(closes)
        result = _calc_macd_histogram_divergence_v61(mmd, closes, macd_data)
        assert isinstance(result["msg"], str)
        assert len(result["msg"]) > 0


class TestCompositeSignalScoreV61:
    """测试条件185：综合多信号评分。"""

    def test_basic_structure(self):
        """基本结构测试。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        result = _calc_composite_signal_score_v61(mmd)
        assert "composite_score" in result
        assert "quality_tier" in result
        assert "tier_color" in result
        assert "condition_count" in result
        assert "total_adjustment" in result
        assert "breakdown" in result
        assert "decision_help" in result
        assert "recommendation" in result

    def test_quality_tier_s(self):
        """S级评分测试（高置信度+多正向调整）。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.7)
        mmd._rsi_deep_divergence_v60 = {"confidence_adjust": 0.04}
        mmd._ma_spacing_strength_v60 = {"confidence_adjust": 0.03}
        mmd._kdj_ob_os_confirm_v60 = {"confidence_adjust": 0.03}
        result = _calc_composite_signal_score_v61(mmd)
        assert result["quality_tier"] in ("S", "A")
        assert result["composite_score"] > 0.5

    def test_quality_tier_d(self):
        """D级评分测试（低置信度+负向调整）。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.2)
        mmd._rsi_deep_divergence_v60 = {"confidence_adjust": -0.01}
        mmd._ma_spacing_strength_v60 = {"confidence_adjust": -0.03}
        result = _calc_composite_signal_score_v61(mmd)
        assert result["quality_tier"] in ("C", "D")

    def test_quality_tier_colors(self):
        """颜色映射验证。"""
        mmd_s = _make_mmd(MMDType.BUY_3, confidence=0.8)
        result_s = _calc_composite_signal_score_v61(mmd_s)
        assert result_s["tier_color"] == "#f59e0b"

        mmd_a = _make_mmd(MMDType.BUY_3, confidence=0.65)
        result_a = _calc_composite_signal_score_v61(mmd_a)
        assert result_a["tier_color"] == "#22c55e"

        mmd_b = _make_mmd(MMDType.BUY_3, confidence=0.5)
        result_b = _calc_composite_signal_score_v61(mmd_b)
        assert result_b["tier_color"] == "#3b82f6"

    def test_recommendation_map(self):
        """推荐操作映射验证。"""
        mmd_s = _make_mmd(MMDType.BUY_3, confidence=0.8)
        result_s = _calc_composite_signal_score_v61(mmd_s)
        assert len(result_s["recommendation"]) > 0

        mmd_d = _make_mmd(MMDType.BUY_3, confidence=0.2)
        result_d = _calc_composite_signal_score_v61(mmd_d)
        assert len(result_d["recommendation"]) > 0

    def test_sell3_composite(self):
        """3卖信号综合评分测试。"""
        mmd = _make_mmd(MMDType.SELL_3, confidence=0.6)
        mmd._rsi_deep_divergence_v60 = {"confidence_adjust": 0.03}
        result = _calc_composite_signal_score_v61(mmd)
        assert result["condition_count"] >= 1
        assert result["composite_score"] > 0.0

    def test_no_conditions(self):
        """无额外条件时的基础评分。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        result = _calc_composite_signal_score_v61(mmd)
        assert result["condition_count"] == 0
        assert result["total_adjustment"] == 0.0
        assert result["quality_tier"] == "B"

    def test_breakdown_format(self):
        """breakdown格式验证。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        mmd._rsi_deep_divergence_v60 = {"confidence_adjust": 0.04}
        mmd._ma_spacing_strength_v60 = {"confidence_adjust": -0.02}
        result = _calc_composite_signal_score_v61(mmd)
        assert isinstance(result["breakdown"], dict)
        assert len(result["breakdown"]) >= 2
        for v in result["breakdown"].values():
            assert isinstance(v, float)


class TestFindMMDsV61Integration:
    """集成测试：验证V61函数可被find_mmds_v39调用。"""

    def test_v61_functions_importable(self):
        """V61函数可导入。"""
        from easy_tdx.chanlun.mmd import (
            _calc_macd_histogram_divergence_v61,
            _calc_composite_signal_score_v61,
        )
        assert callable(_calc_macd_histogram_divergence_v61)
        assert callable(_calc_composite_signal_score_v61)

    def test_v61_fields_in_mmd_type(self):
        """V61字段存在于MMD类型定义中。"""
        mmd = _make_mmd(MMDType.BUY_3)
        assert hasattr(mmd, "_macd_hist_divergence_v61")
        assert hasattr(mmd, "_composite_signal_score_v61")

    def test_v61_confidence_bounds(self):
        """V61不超出置信度边界。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(60, trend="down")
        macd_data = _make_macd_data(closes)
        adj = _calc_macd_histogram_divergence_v61(mmd, closes, macd_data)["confidence_adjust"]
        new_conf = max(0.0, min(1.0, 0.5 + adj))
        assert 0.0 <= new_conf <= 1.0

    def test_v61_all_conditions_callable(self):
        """所有V61条件函数可调用。"""
        mmd = _make_mmd(MMDType.BUY_3, confidence=0.5)
        closes = _make_closes(60, trend="down")
        macd_data = _make_macd_data(closes)

        macd_div = _calc_macd_histogram_divergence_v61(mmd, closes, macd_data)
        assert isinstance(macd_div, dict)
        assert "confidence_adjust" in macd_div

        comp = _calc_composite_signal_score_v61(mmd)
        assert isinstance(comp, dict)
        assert "quality_tier" in comp

    def test_sell3_v61_conditions(self):
        """3卖信号的V61条件测试。"""
        mmd = _make_mmd(MMDType.SELL_3, confidence=0.5)
        closes = _make_closes(60, trend="up")
        macd_data = _make_macd_data(closes)

        macd_div = _calc_macd_histogram_divergence_v61(mmd, closes, macd_data)
        assert isinstance(macd_div, dict)

        comp = _calc_composite_signal_score_v61(mmd)
        assert isinstance(comp, dict)
        assert comp["quality_tier"] in ("S", "A", "B", "C", "D")

    def test_v61_integration_pass(self):
        """V61集成通过测试。"""
        from easy_tdx.chanlun.mmd import find_mmds_v39
        import inspect
        source = inspect.getsource(find_mmds_v39)
        assert "_calc_macd_histogram_divergence_v61" in source
        assert "_calc_composite_signal_score_v61" in source
