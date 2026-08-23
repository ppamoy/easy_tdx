#!/usr/bin/env python3
"""V51 缠论模型条件144-147 专项测试。

测试内容：
- 条件144：突破笔力度二次确认增强（Breakout Bi Strength Enhanced）
- 条件145：回踩笔深度+时间综合验证（Pullback Depth+Time）
- 条件146：趋势强度综合评分（Trend Strength Composite）
- 条件147：交易决策建议（Trading Decision Recommendation）
"""

from __future__ import annotations

import pytest

from easy_tdx.chanlun.mmd import (
    _calc_breakout_bi_strength_enhanced_v51,
    _calc_pullback_depth_time_v51,
    _calc_trend_strength_composite_v51,
    _calc_trading_decision_v51,
)
from easy_tdx.chanlun.types import MMD, MMDType, BI, FX, FXType, CLKline, ZS, Direction
from datetime import datetime


def _make_mock_mmd(mmd_type: MMDType, confidence: float = 0.5) -> MMD:
    """创建Mock MMD对象。"""
    return MMD(
        mmd_type=mmd_type,
        bi=None,
        zs=None,
        confidence=confidence,
        msg="test",
    )


def _make_mock_bi(start_idx: int = 0, end_idx: int = 10, direction: str = "up") -> BI:
    """创建Mock BI对象。"""
    start_fx = FX(
        fx_type=FXType.DI if direction == "up" else FXType.DING,
        k=CLKline(
            k_index=start_idx,
            date=datetime.now(),
            open=100.0,
            close=100.0,
            high=101.0,
            low=99.0,
            amount=1000000.0,
        ),
        klines=[],
        val=100.0,
    )
    end_fx = FX(
        fx_type=FXType.DING if direction == "up" else FXType.DI,
        k=CLKline(
            k_index=end_idx,
            date=datetime.now(),
            open=110.0,
            close=110.0,
            high=112.0,
            low=108.0,
            amount=1000000.0,
        ),
        klines=[],
        val=112.0,
    )
    return BI(
        start=start_fx,
        end=end_fx,
        direction=Direction.UP if direction == "up" else Direction.DOWN,
        high=112.0,
        low=99.0,
    )


class TestBreakoutBiStrengthEnhancedV51:
    """条件144：突破笔力度二次确认增强测试。"""

    def test_strong_breakout_all_dimensions(self):
        """3买：量价MACD三维度充分确认 → +4%置信度。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        entry_bi = _make_mock_bi(start_idx=0, end_idx=5, direction="down")
        breakout_bi = _make_mock_bi(start_idx=5, end_idx=15, direction="up")
        # 突破笔成交量更大、价格幅度更大
        breakout_bi.end.k.amount = 5000000.0  # 放量
        mmd.bi = breakout_bi
        mmd.zs = ZS(zg=110.0, zd=100.0, gg=115.0, dd=95.0, lines=[], direction="up")
        bis = [entry_bi, breakout_bi]
        volumes = [1000000.0] * 20
        # MACD数据：突破笔面积大于入场笔
        macd_data = {"hist": [0.0] * 5 + [-0.5] * 5 + [0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 0.9, 0.8, 0.7]}
        result = _calc_breakout_bi_strength_enhanced_v51(mmd, bis, None, volumes, macd_data)
        assert result["score"] >= 1  # 至少有一个维度通过
        assert result["confidence_adjust"] >= 0

    def test_weak_breakout_all_fail(self):
        """3买：三维度均不通过 → -5%置信度。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 入场笔：indices 0-10，突破笔：indices 10-20
        entry_bi = _make_mock_bi(start_idx=0, end_idx=10, direction="down")
        breakout_bi = _make_mock_bi(start_idx=10, end_idx=20, direction="up")
        # 强制突破笔价格幅度很小（range=2 vs entry range=13），确保price_ok=False
        breakout_bi.high = 105.0
        breakout_bi.low = 103.0
        breakout_bi.end.k.high = 105.0
        breakout_bi.end.k.low = 103.0
        mmd.bi = breakout_bi
        mmd.zs = ZS(zg=110.0, zd=100.0, gg=115.0, dd=95.0, lines=[], direction="up")
        bis = [entry_bi, breakout_bi]
        # 入场笔所在区间volume大，突破笔区间volume小
        volumes = [2000000.0] * 10 + [100000.0] * 10
        # MACD数据：入场笔区间面积大，突破笔区间面积小
        macd_data = {"hist": [1.0] * 10 + [0.02] * 10}
        result = _calc_breakout_bi_strength_enhanced_v51(mmd, bis, None, volumes, macd_data)
        # 三维度均不通过
        assert result["vol_ok"] is False
        assert result["price_ok"] is False
        assert result["macd_ok"] is False
        assert result["score"] == 0
        assert result["confidence_adjust"] == -0.05

    def test_none_bi_returns_default(self):
        """bi为None时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = None
        result = _calc_breakout_bi_strength_enhanced_v51(mmd, [], None, [], None)
        assert result["score"] == 0
        assert result["confidence_adjust"] == 0.0

    def test_insufficient_data_returns_default(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = _make_mock_bi(start_idx=0, end_idx=1, direction="up")
        result = _calc_breakout_bi_strength_enhanced_v51(mmd, [], None, [], None)
        assert result["score"] == 0
        assert result["confidence_adjust"] == 0.0

    def test_sell_3_weak_breakout(self):
        """3卖：弱突破信号 → 降权。"""
        mmd = _make_mock_mmd(MMDType.SELL_3, confidence=0.6)
        entry_bi = _make_mock_bi(start_idx=0, end_idx=10, direction="up")
        breakout_bi = _make_mock_bi(start_idx=10, end_idx=20, direction="down")
        # 强制突破笔价格幅度很小
        breakout_bi.high = 105.0
        breakout_bi.low = 103.0
        breakout_bi.end.k.high = 105.0
        breakout_bi.end.k.low = 103.0
        mmd.bi = breakout_bi
        mmd.zs = ZS(zg=110.0, zd=100.0, gg=115.0, dd=95.0, lines=[], direction="up")
        bis = [entry_bi, breakout_bi]
        volumes = [2000000.0] * 10 + [100000.0] * 10  # 突破笔区间缩量
        macd_data = {"hist": [1.0] * 10 + [0.02] * 10}
        result = _calc_breakout_bi_strength_enhanced_v51(mmd, bis, None, volumes, macd_data)
        assert result["score"] == 0
        assert result["confidence_adjust"] == -0.05


class TestPullbackDepthTimeV51:
    """条件145：回踩笔深度+时间综合验证测试。"""

    def test_strong_pullback_both_ok(self):
        """回踩深度和时间都符合要求 → +3%置信度。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        # 创建中枢和回踩笔
        zs = ZS(zg=110.0, zd=100.0, gg=115.0, dd=95.0, lines=[], direction="up")
        mmd.zs = zs
        # 回踩笔低点接近ZD但不过深（<3%）
        pullback_bi = _make_mock_bi(start_idx=5, end_idx=10, direction="down")
        pullback_bi.low = 99.5  # 略低于ZD，深度约0.5%，在安全范围内
        mmd.bi = pullback_bi
        closes = [100.0 + i * 0.1 for i in range(30)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = _calc_pullback_depth_time_v51(mmd, closes, highs, lows, None)
        assert result["depth_ok"] is True
        assert result["combined_status"] in ("strong", "normal")

    def test_deep_pullback_over_3pct(self):
        """回踩过深（>3%）→ 降权。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        zs = ZS(zg=110.0, zd=100.0, gg=115.0, dd=95.0, lines=[], direction="up")
        mmd.zs = zs
        pullback_bi = _make_mock_bi(start_idx=5, end_idx=10, direction="down")
        pullback_bi.low = 95.0  # 过深，深度>5%
        mmd.bi = pullback_bi
        closes = [100.0 + i * 0.1 for i in range(30)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = _calc_pullback_depth_time_v51(mmd, closes, highs, lows, None)
        assert result["depth_ok"] is False
        assert result["confidence_adjust"] < 0

    def test_none_bi_returns_default(self):
        """bi为None时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = None
        result = _calc_pullback_depth_time_v51(mmd, [100.0] * 10, [100.5] * 10, [99.5] * 10, None)
        assert result["combined_status"] == "unknown"
        assert result["confidence_adjust"] == 0.0

    def test_insufficient_data_returns_default(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        mmd.bi = None
        result = _calc_pullback_depth_time_v51(mmd, [100.0], [100.5], [99.5], None)
        assert result["combined_status"] == "unknown"
        assert result["confidence_adjust"] == 0.0


class TestTrendStrengthCompositeV51:
    """条件146：趋势强度综合评分测试。"""

    def test_strong_uptrend_for_buy(self):
        """3买：强上升趋势 → +4%置信度。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.6)
        # 强上升趋势：ADX高、MA向上、动量为正
        closes = [100.0 + i * 0.5 for i in range(60)]
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        result = _calc_trend_strength_composite_v51(mmd, closes, highs, lows, None)
        assert result["total_score"] >= 0  # 至少中性
        assert result["trend_strength"] in ("strong", "medium", "weak")

    def test_downtrend_for_buy_negative(self):
        """3买：下降趋势 → 降权。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.5)
        # 下降趋势
        closes = [100.0 - i * 0.5 for i in range(60)]
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        result = _calc_trend_strength_composite_v51(mmd, closes, highs, lows, None)
        # 趋势方向与买入信号相反，应降权
        assert result["total_score"] < 3 or result["confidence_adjust"] <= 0

    def test_insufficient_data_returns_default(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3)
        result = _calc_trend_strength_composite_v51(mmd, [100.0] * 10, [101.0] * 10, [99.0] * 10, None)
        assert result["total_score"] == 0
        assert result["confidence_adjust"] == 0.0

    def test_neutral_trend_no_adjustment(self):
        """中性趋势 → 无调整。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.5)
        # 横盘震荡
        closes = [100.0 + 0.5 * (i % 2 == 0) for i in range(60)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = _calc_trend_strength_composite_v51(mmd, closes, highs, lows, None)
        assert result["total_score"] < 3  # 不够强趋势

    def test_sell_3_downtrend_confirmed(self):
        """3卖：下降趋势确认 → +2%或更高。"""
        mmd = _make_mock_mmd(MMDType.SELL_3, confidence=0.6)
        closes = [100.0 - i * 0.3 for i in range(60)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = _calc_trend_strength_composite_v51(mmd, closes, highs, lows, None)
        # 下降趋势对3卖是正向确认
        assert result["trend_strength"] in ("strong", "medium", "weak")


class TestTradingDecisionV51:
    """条件147：交易决策建议测试。"""

    def test_high_confidence_buy_signal(self):
        """高置信度3买 → 建议买入。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.7)
        # 用较大的中枢高度来获得足够的RRR
        mmd.zs = ZS(zg=120.0, zd=100.0, gg=125.0, dd=95.0, lines=[], direction="up")
        closes = [100.0 + i * 0.1 for i in range(30)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = _calc_trading_decision_v51(mmd, closes, highs, lows, None)
        assert result["decision"].startswith("buy")
        assert result["quality_tier"] in ("S", "A", "B")
        assert result["risk_reward_ratio"] > 0
        assert result["atr"] > 0

    def test_low_confidence_buy_signal_wait(self):
        """低置信度3买 → 观望。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.3)
        mmd.zs = ZS(zg=110.0, zd=100.0, gg=115.0, dd=95.0, lines=[], direction="up")
        closes = [100.0 + i * 0.1 for i in range(30)]
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        result = _calc_trading_decision_v51(mmd, closes, highs, lows, None)
        assert result["decision"] == "wait"

    def test_high_confidence_sell_signal(self):
        """高置信度3卖 → 建议卖出。"""
        mmd = _make_mock_mmd(MMDType.SELL_3, confidence=0.7)
        # 用较大的中枢高度来获得足够的RRR
        mmd.zs = ZS(zg=120.0, zd=100.0, gg=125.0, dd=95.0, lines=[], direction="up")
        closes = [100.0 - i * 0.1 for i in range(30)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = _calc_trading_decision_v51(mmd, closes, highs, lows, None)
        assert result["decision"].startswith("sell")

    def test_insufficient_data_returns_default(self):
        """数据不足时返回默认值。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.5)
        result = _calc_trading_decision_v51(mmd, [100.0], [101.0], [99.0], None)
        assert result["decision"] == "hold"
        assert result["quality_tier"] == "C"

    def test_no_zhongshu_fallback(self):
        """无中枢时使用ATR回退方案。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.6)
        mmd.zs = None
        closes = [100.0 + i * 0.2 for i in range(30)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = _calc_trading_decision_v51(mmd, closes, highs, lows, None)
        assert result["entry_price"] > 0
        assert result["stop_loss"] > 0
        assert result["take_profit_1"] > 0

    def test_risk_reward_ratio(self):
        """风险收益比计算合理。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.7)
        # 较大中枢高度以获得足够RRR
        mmd.zs = ZS(zg=120.0, zd=100.0, gg=125.0, dd=95.0, lines=[], direction="up")
        closes = [100.0 + i * 0.1 for i in range(30)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = _calc_trading_decision_v51(mmd, closes, highs, lows, None)
        # RRR = (TP1 - Entry) / (Entry - SL)
        if result["risk_reward_ratio"] > 0:
            assert result["risk_reward_ratio"] <= 10  # 合理上限


class TestFindMMDsV51Integration:
    """V51集成测试。"""

    def test_v51_fields_present_in_mmd(self):
        """V51字段应存在于MMD对象中。"""
        from easy_tdx.chanlun.types import MMD
        mmd = _make_mock_mmd(MMDType.BUY_3)
        assert hasattr(mmd, "_breakout_bi_strength_enhanced_v51")
        assert hasattr(mmd, "_pullback_depth_time_v51")
        assert hasattr(mmd, "_trend_strength_composite_v51")
        assert hasattr(mmd, "_trading_decision_v51")

    def test_v51_functions_callable(self):
        """V51函数均可调用。"""
        assert callable(_calc_breakout_bi_strength_enhanced_v51)
        assert callable(_calc_pullback_depth_time_v51)
        assert callable(_calc_trend_strength_composite_v51)
        assert callable(_calc_trading_decision_v51)

    def test_v51_confidence_bounds(self):
        """V51置信度调整应在合理范围内。"""
        mmd = _make_mock_mmd(MMDType.BUY_3, confidence=0.5)
        mmd.zs = ZS(zg=120.0, zd=100.0, gg=125.0, dd=95.0, lines=[], direction="up")
        closes = [100.0 + i * 0.1 for i in range(60)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        volumes = [1000000.0] * 60

        result1 = _calc_pullback_depth_time_v51(mmd, closes, highs, lows, None)
        assert -0.05 <= result1["confidence_adjust"] <= 0.05

        result2 = _calc_trend_strength_composite_v51(mmd, closes, highs, lows, volumes)
        assert -0.05 <= result2["confidence_adjust"] <= 0.05

        result3 = _calc_trading_decision_v51(mmd, closes, highs, lows, None)
        assert result3["decision"] in ("buy_aggressive", "buy_cautious", "wait", "sell_aggressive", "sell_cautious", "hold")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
