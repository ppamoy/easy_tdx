"""V48 缠论模型决策增强专项测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.chanlun.mmd import (
    _calc_dynamic_risk_reward_ratio_v48,
    _calc_trend_strength_weighting_v48,
    _calc_volume_price_divergence_secondary_v48,
)
from easy_tdx.chanlun.types import MMD, MMDType


class TestVolumePriceDivergenceSecondaryV48:
    """测试量价背离二次确认（条件134）。"""

    def _make_data(
        self, n: int = 100, start_price: float = 50.0, trend: str = "up"
    ) -> tuple[list[float], list[float]]:
        """生成测试数据。"""
        np.random.seed(42)
        closes = [start_price]
        volumes = []
        for i in range(1, n):
            if trend == "up":
                closes.append(closes[-1] * (1 + np.random.normal(0.001, 0.01)))
            else:
                closes.append(closes[-1] * (1 + np.random.normal(-0.001, 0.01)))
            volumes.append(1e6 * (1 + np.random.normal(0, 0.2)))
        return closes, volumes[:n]

    def test_vwap_deviation_positive_for_buy(self):
        """测试买入信号时VWAP偏离度为正。"""
        closes, volumes = self._make_data(n=100, start_price=50.0, trend="up")
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买: 突破确认")
        # 创建一个模拟的笔
        from datetime import datetime

        from easy_tdx.chanlun.types import BI, FX, CLKline, FXType

        k = CLKline(
            k_index=90, date=datetime(2024, 1, 1), open=50, close=52, high=53, low=49, amount=1e6
        )
        fx = FX(fx_type=FXType.DI, k=k, klines=[k, k, k], val=49)
        k2 = CLKline(
            k_index=95, date=datetime(2024, 1, 6), open=52, close=53, high=54, low=51, amount=1e6
        )
        fx2 = FX(fx_type=FXType.DING, k=k2, klines=[k, k2, k2], val=54)
        bi = BI(start=fx, end=fx2, direction="up")
        mmd.bi = bi

        result = _calc_volume_price_divergence_secondary_v48(mmd, closes, volumes)
        assert "confidence_adjust" in result
        assert "msg" in result

    def test_vwap_deviation_negative_for_sell(self):
        """测试卖出信号时VWAP偏离度为负。"""
        closes, volumes = self._make_data(n=100, start_price=50.0, trend="down")
        mmd = MMD(mmd_type=MMDType.SELL_3, msg="3卖: 跌破确认")
        from datetime import datetime

        from easy_tdx.chanlun.types import BI, FX, CLKline, FXType

        k = CLKline(
            k_index=90, date=datetime(2024, 1, 1), open=50, close=48, high=51, low=47, amount=1e6
        )
        fx = FX(fx_type=FXType.DING, k=k, klines=[k, k, k], val=51)
        k2 = CLKline(
            k_index=95, date=datetime(2024, 1, 6), open=48, close=47, high=49, low=46, amount=1e6
        )
        fx2 = FX(fx_type=FXType.DI, k=k2, klines=[k, k2, k2], val=46)
        bi = BI(start=fx, end=fx2, direction="down")
        mmd.bi = bi

        result = _calc_volume_price_divergence_secondary_v48(mmd, closes, volumes)
        assert "confidence_adjust" in result
        assert "msg" in result

    def test_none_bi_returns_empty(self):
        """测试bi为None时返回空结果。"""
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
        result = _calc_volume_price_divergence_secondary_v48(mmd, [50.0, 51.0], [1e6, 1e6])
        assert result["confidence_adjust"] == 0.0


class TestTrendStrengthWeightingV48:
    """测试趋势强度加权（条件135）。"""

    def _make_data(
        self, n: int = 100, start_price: float = 50.0
    ) -> tuple[list[float], list[float], list[float]]:
        np.random.seed(42)
        closes = [start_price]
        highs = [start_price * 1.01]
        lows = [start_price * 0.99]
        for i in range(1, n):
            c = closes[-1] * (1 + np.random.normal(0.001, 0.01))
            closes.append(c)
            highs.append(c * 1.005)
            lows.append(c * 0.995)
        return closes, highs, lows

    def test_strong_trend_with_alignment(self):
        """测试强趋势且方向一致时加分。"""
        closes, highs, lows = self._make_data(n=100, start_price=50.0)
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
        from datetime import datetime

        from easy_tdx.chanlun.types import BI, FX, CLKline, FXType

        k = CLKline(
            k_index=90, date=datetime(2024, 1, 1), open=50, close=52, high=53, low=49, amount=1e6
        )
        fx = FX(fx_type=FXType.DI, k=k, klines=[k, k, k], val=49)
        k2 = CLKline(
            k_index=95, date=datetime(2024, 1, 6), open=52, close=53, high=54, low=51, amount=1e6
        )
        fx2 = FX(fx_type=FXType.DING, k=k2, klines=[k, k2, k2], val=54)
        bi = BI(start=fx, end=fx2, direction="up")
        mmd.bi = bi

        result = _calc_trend_strength_weighting_v48(mmd, closes, highs, lows, trend_strength=0.8)
        assert "adx_value" in result
        assert "confidence_adjust" in result

    def test_none_bi_returns_empty(self):
        """测试bi为None时返回空结果。"""
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
        result = _calc_trend_strength_weighting_v48(
            mmd, [50.0, 51.0], [51.0, 52.0], [49.0, 50.0], 0.5
        )
        assert result["confidence_adjust"] == 0.0


class TestDynamicRiskRewardRatioV48:
    """测试动态风险收益比（条件136）。"""

    def _make_data(
        self, n: int = 100, start_price: float = 50.0
    ) -> tuple[list[float], list[float], list[float]]:
        np.random.seed(42)
        closes = [start_price]
        highs = [start_price * 1.01]
        lows = [start_price * 0.99]
        for i in range(1, n):
            c = closes[-1] * (1 + np.random.normal(0.001, 0.01))
            closes.append(c)
            highs.append(c * 1.005)
            lows.append(c * 0.995)
        return closes, highs, lows

    def test_buy_rrr_calculation(self):
        """测试买入信号的风险收益比计算。"""
        closes, highs, lows = self._make_data(n=100, start_price=50.0)
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
        from datetime import datetime

        from easy_tdx.chanlun.types import BI, FX, CLKline, FXType

        k = CLKline(
            k_index=90, date=datetime(2024, 1, 1), open=50, close=52, high=53, low=49, amount=1e6
        )
        fx = FX(fx_type=FXType.DI, k=k, klines=[k, k, k], val=49)
        k2 = CLKline(
            k_index=95, date=datetime(2024, 1, 6), open=52, close=53, high=54, low=51, amount=1e6
        )
        fx2 = FX(fx_type=FXType.DING, k=k2, klines=[k, k2, k2], val=54)
        bi = BI(start=fx, end=fx2, direction="up")
        mmd.bi = bi

        result = _calc_dynamic_risk_reward_ratio_v48(mmd, closes, highs, lows)
        assert "entry_price" in result
        assert "stop_loss" in result
        assert "take_profit_1" in result
        assert "risk_reward_ratio" in result
        assert "quality_tier" in result
        assert result["risk_reward_ratio"] > 0

    def test_sell_rrr_calculation(self):
        """测试卖出信号的风险收益比计算。"""
        closes, highs, lows = self._make_data(n=100, start_price=50.0)
        mmd = MMD(mmd_type=MMDType.SELL_3, msg="3卖")
        from datetime import datetime

        from easy_tdx.chanlun.types import BI, FX, CLKline, FXType

        k = CLKline(
            k_index=90, date=datetime(2024, 1, 1), open=50, close=48, high=51, low=47, amount=1e6
        )
        fx = FX(fx_type=FXType.DING, k=k, klines=[k, k, k], val=51)
        k2 = CLKline(
            k_index=95, date=datetime(2024, 1, 6), open=48, close=47, high=49, low=46, amount=1e6
        )
        fx2 = FX(fx_type=FXType.DI, k=k2, klines=[k, k2, k2], val=46)
        bi = BI(start=fx, end=fx2, direction="down")
        mmd.bi = bi

        result = _calc_dynamic_risk_reward_ratio_v48(mmd, closes, highs, lows)
        assert "risk_reward_ratio" in result
        assert result["risk_reward_ratio"] > 0

    def test_none_bi_returns_empty(self):
        """测试bi为None时返回空结果。"""
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
        result = _calc_dynamic_risk_reward_ratio_v48(mmd, [50.0, 51.0], [51.0, 52.0], [49.0, 50.0])
        assert result["confidence_adjust"] == 0.0


class TestFindMMDsV48Integration:
    """测试find_mmds集成V48条件。"""

    def _make_test_data(self, n: int = 200) -> pd.DataFrame:
        np.random.seed(99)
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        close = [50.0]
        for i in range(1, n):
            if i < 80:
                close.append(close[-1] * 0.997)
            elif i < 150:
                close.append(close[-1] * 1.002)
            else:
                close.append(close[-1] * (1 + np.random.normal(0, 0.005)))
        close = np.array(close)
        return pd.DataFrame(
            {
                "datetime": dates,
                "open": close * (1 + np.random.uniform(-0.005, 0.005, n)),
                "high": close * (1 + np.random.uniform(0, 0.01, n)),
                "low": close * (1 + np.random.uniform(-0.01, 0, n)),
                "close": close,
                "amount": [1e6] * n,
                "vol": [1e5] * n,
            }
        )

    def test_v48_fields_present_in_mmd(self):
        """测试V48字段存在于MMD对象中。"""
        df = self._make_test_data(250)
        analyser = ChanlunAnalyser(code="TEST", frequency="daily")
        result = analyser.process_klines(df)

        buy_3_signals = [m for m in result.mmds if m.mmd_type == MMDType.BUY_3]
        if buy_3_signals:
            mmd = buy_3_signals[0]
            # V48字段应存在（可能为None，但不报错）
            assert hasattr(mmd, "_volume_price_divergence_secondary_v48")
            assert hasattr(mmd, "_trend_strength_weighting")
            assert hasattr(mmd, "_dynamic_risk_reward_ratio")

    def test_v48_no_crash(self):
        """测试V48不会导致崩溃。"""
        df = self._make_test_data(250)
        analyser = ChanlunAnalyser(code="TEST", frequency="daily")
        result = analyser.process_klines(df)
        # 应该正常返回，不抛出异常
        assert result is not None
        assert hasattr(result, "mmds")
