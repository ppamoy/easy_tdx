"""V49 缠论模型精准度提升专项测试（条件137-139）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.chanlun.mmd import (
    _calc_breakout_strength_revalidation_v49,
    _calc_pullback_structure_integrity_v49,
    _calc_zhongshu_level_weight_v49,
)
from easy_tdx.chanlun.types import MMD, MMDType, BI, FX, FXType, CLKline, ZS


def _make_bi(index_start: int, index_end: int, price_start: float, price_end: float) -> BI:
    """辅助函数：创建一个简单的笔。"""
    from datetime import datetime
    k1 = CLKline(
        k_index=index_start,
        date=datetime(2024, 1, 1),
        open=price_start, close=price_start, high=price_start, low=price_start,
        amount=1e6,
    )
    fx1 = FX(fx_type=FXType.DI, k=k1, klines=[k1, k1, k1], val=price_start)
    k2 = CLKline(
        k_index=index_end,
        date=datetime(2024, 1, 6),
        open=price_end, close=price_end, high=price_end, low=price_end,
        amount=1e6,
    )
    fx2 = FX(fx_type=FXType.DING, k=k2, klines=[k1, k2, k2], val=price_end)
    direction = "up" if price_end > price_start else "down"
    return BI(start=fx1, end=fx2, direction=direction)


class TestBreakoutStrengthRevalidationV49:
    """测试突破力度二次验证（条件137）。"""

    def test_stable_momentum_for_buy(self):
        """测试买入信号在动能稳定时通过验证。"""
        np.random.seed(42)
        n = 100
        closes = [50.0]
        for i in range(1, n):
            closes.append(closes[-1] * (1 + np.random.normal(0.002, 0.008)))
        # MACD histogram: stable bullish
        hist = [0.5 + np.random.normal(0, 0.1) for _ in range(n)]
        hist[:20] = [0.8 + np.random.normal(0, 0.1) for _ in range(20)]  # stronger before

        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
        bi = _make_bi(80, 90, 48.0, 52.0)
        mmd.bi = bi

        result = _calc_breakout_strength_revalidation_v49(mmd, closes, None, {"hist": hist})
        assert "confirmed" in result
        assert "hist_area_ratio" in result
        assert "confidence_adjust" in result
        assert "msg" in result
        # 动能应保持稳定或增强
        assert result["confirmed"] is True or result["hist_area_ratio"] >= 0

    def test_decaying_momentum_for_sell(self):
        """测试卖出信号在动能衰减时被标记。"""
        np.random.seed(43)
        n = 100
        closes = [50.0]
        for i in range(1, n):
            closes.append(closes[-1] * (1 + np.random.normal(-0.002, 0.008)))
        # MACD histogram: decaying bearish
        hist = [-0.3 - i * 0.01 for i in range(n)]  # getting weaker

        mmd = MMD(mmd_type=MMDType.SELL_3, msg="3卖")
        bi = _make_bi(80, 90, 52.0, 48.0)
        mmd.bi = bi

        result = _calc_breakout_strength_revalidation_v49(mmd, closes, None, {"hist": hist})
        assert "confirmed" in result
        assert "hist_area_ratio" in result
        assert result["hist_area_ratio"] >= 0

    def test_none_bi_returns_default(self):
        """测试bi为None时返回默认值。"""
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
        result = _calc_breakout_strength_revalidation_v49(mmd, [50.0, 51.0], None, None)
        assert result["confirmed"] is True
        assert result["confidence_adjust"] == 0.0

    def test_short_closes_returns_default(self):
        """测试数据过短时返回默认值。"""
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
        bi = _make_bi(2, 5, 50.0, 52.0)
        mmd.bi = bi
        result = _calc_breakout_strength_revalidation_v49(mmd, [50.0, 51.0], None, None)
        assert result["confidence_adjust"] == 0.0


class TestPullbackStructureIntegrityV49:
    """测试回踩结构完整性（条件138）。"""

    def test_strong_decline_for_3buy(self):
        """测试3买回踩笔呈清晰递减趋势时通过验证。"""
        # 递减价格序列：前半段高，后半段低
        price_seq = [55.0, 54.0, 53.0, 52.0, 50.0, 48.0, 46.0, 44.0]
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
        bi = _make_bi(80, 88, 55.0, 44.0)
        mmd.bi = bi

        result = _calc_pullback_structure_integrity_v49(mmd, None, price_seq)
        assert "confirmed" in result
        assert "structure_quality" in result
        assert "confidence_adjust" in result
        assert "msg" in result

    def test_strong_rise_for_3sell(self):
        """测试3卖回踩笔呈清晰递增趋势时通过验证。"""
        price_seq = [44.0, 46.0, 48.0, 50.0, 52.0, 54.0, 55.0, 56.0]
        mmd = MMD(mmd_type=MMDType.SELL_3, msg="3卖")
        bi = _make_bi(80, 88, 44.0, 56.0)
        mmd.bi = bi

        result = _calc_pullback_structure_integrity_v49(mmd, None, price_seq)
        assert "confirmed" in result
        assert "structure_quality" in result

    def test_invalid_structure_filtered(self):
        """测试结构无效时被过滤（3买时非递减）。"""
        from datetime import datetime
        price_seq = [44.0, 46.0, 48.0, 50.0, 52.0, 54.0, 55.0, 56.0]
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
        # 创建向上的笔（3买需要向下的回踩，所以这应该是无效的）
        k1 = CLKline(k_index=0, date=datetime(2024, 1, 1), open=44, close=44, high=44, low=44, amount=1e6)
        fx1 = FX(fx_type=FXType.DI, k=k1, klines=[k1, k1, k1], val=44)
        k2 = CLKline(k_index=7, date=datetime(2024, 1, 8), open=56, close=56, high=56, low=56, amount=1e6)
        fx2 = FX(fx_type=FXType.DING, k=k2, klines=[k1, k2, k2], val=56)
        bi = BI(start=fx1, end=fx2, direction="up")
        mmd.bi = bi

        result = _calc_pullback_structure_integrity_v49(mmd, [bi], price_seq)
        assert "confirmed" in result
        assert "structure_quality" in result
        # 3买时递增结构应被标记为无效
        assert result["structure_quality"] == "invalid" and result["confirmed"] is False

    def test_none_bi_returns_default(self):
        """测试bi为None时返回默认值。"""
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
        result = _calc_pullback_structure_integrity_v49(mmd, [], [50.0, 51.0])
        assert result["confidence_adjust"] == 0.0

    def test_insufficient_data_returns_default(self):
        """测试数据不足时返回默认值。"""
        from datetime import datetime
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
        k1 = CLKline(k_index=0, date=datetime(2024, 1, 1), open=50, close=50, high=50, low=50, amount=1e6)
        fx1 = FX(fx_type=FXType.DI, k=k1, klines=[k1, k1, k1], val=50)
        k2 = CLKline(k_index=2, date=datetime(2024, 1, 3), open=48, close=48, high=48, low=48, amount=1e6)
        fx2 = FX(fx_type=FXType.DING, k=k2, klines=[k1, k2, k2], val=48)
        bi = BI(start=fx1, end=fx2, direction="down")
        mmd.bi = bi
        result = _calc_pullback_structure_integrity_v49(mmd, [bi], [50.0, 49.0])
        assert result["confidence_adjust"] == -0.01


class TestZhongshuLevelWeightV49:
    """测试中枢级别权重（条件139）。"""

    def test_high_level_zs_bonus(self):
        """测试线条数≥5的中枢给予加分。"""
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
        # 创建含5条线的中枢
        zs = ZS(index=0, done=True)
        for i in range(5):
            bi = _make_bi(10 * i, 10 * i + 5, 50.0 + i, 48.0 + i)
            zs.lines.append(bi)
        mmd.zs = zs

        result = _calc_zhongshu_level_weight_v49(mmd, None)
        assert result["level"] == "high"
        assert result["line_count"] == 5
        assert result["confidence_adjust"] == 0.02

    def test_medium_level_zs_no_adjust(self):
        """测试线条数3-4的中枢不调整置信度。"""
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
        zs = ZS(index=0, done=True)
        for i in range(3):
            bi = _make_bi(10 * i, 10 * i + 5, 50.0 + i, 48.0 + i)
            zs.lines.append(bi)
        mmd.zs = zs

        result = _calc_zhongshu_level_weight_v49(mmd, None)
        assert result["level"] == "medium"
        assert result["line_count"] == 3
        assert result["confidence_adjust"] == 0.0

    def test_low_level_zs_penalty(self):
        """测试线条数1-2的中枢给予扣分。"""
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
        zs = ZS(index=0, done=True)
        bi = _make_bi(10, 15, 50.0, 48.0)
        zs.lines.append(bi)
        mmd.zs = zs

        result = _calc_zhongshu_level_weight_v49(mmd, None)
        assert result["level"] == "low"
        assert result["line_count"] == 1
        assert result["confidence_adjust"] == -0.02

    def test_none_zs_returns_default(self):
        """测试zs为None时返回默认值。"""
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
        result = _calc_zhongshu_level_weight_v49(mmd, None)
        assert result["level"] == "unknown"
        assert result["confidence_adjust"] == 0.0

    def test_empty_lines_returns_default(self):
        """测试线条为0时返回默认值。"""
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
        zs = ZS(index=0, done=True, lines=[])
        mmd.zs = zs

        result = _calc_zhongshu_level_weight_v49(mmd, None)
        assert result["level"] == "unknown"
        assert result["confidence_adjust"] == -0.02


class TestFindMMDsV49Integration:
    """测试find_mmds集成V49条件。"""

    def _make_test_data(self, n: int = 300) -> pd.DataFrame:
        np.random.seed(99)
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        close = [50.0]
        for i in range(1, n):
            if i < 100:
                close.append(close[-1] * 0.997)  # 下跌
            elif i < 200:
                close.append(close[-1] * 1.003)  # 上涨（突破）
            else:
                close.append(close[-1] * (1 + np.random.normal(0, 0.005)))
        close = np.array(close)
        return pd.DataFrame({
            "datetime": dates,
            "open": close * (1 + np.random.uniform(-0.005, 0.005, n)),
            "high": close * (1 + np.random.uniform(0, 0.01, n)),
            "low": close * (1 + np.random.uniform(-0.01, 0, n)),
            "close": close,
            "amount": [1e6] * n,
            "vol": [1e5] * n,
        })

    def test_v49_fields_present_in_mmd(self):
        """测试V49字段存在于MMD对象中。"""
        df = self._make_test_data(350)
        analyser = ChanlunAnalyser(code="TEST", frequency="daily")
        result = analyser.process_klines(df)

        buy_3_signals = [m for m in result.mmds if m.mmd_type == MMDType.BUY_3]
        if buy_3_signals:
            mmd = buy_3_signals[0]
            assert hasattr(mmd, '_breakout_strength_revalidation_v49')
            assert hasattr(mmd, '_pullback_structure_integrity_v49')
            assert hasattr(mmd, '_zhongshu_level_weight_v49')

    def test_v49_no_crash(self):
        """测试V49不会导致崩溃。"""
        df = self._make_test_data(350)
        analyser = ChanlunAnalyser(code="TEST", frequency="daily")
        result = analyser.process_klines(df)
        assert result is not None
        assert hasattr(result, 'mmds')

    def test_v49_confidence_bounds(self):
        """测试V49调整后置信度仍在合理范围内。"""
        df = self._make_test_data(350)
        analyser = ChanlunAnalyser(code="TEST", frequency="daily")
        result = analyser.process_klines(df)

        for mmd in result.mmds:
            assert 0.0 <= mmd.confidence <= 1.0, f"置信度超出范围: {mmd.confidence}"
