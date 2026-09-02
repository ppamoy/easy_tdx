"""V102 决策支持建议执行模拟器测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

from easy_tdx.backtest.advice_simulator import simulate_advice_batch, simulate_advice_trade
from easy_tdx.chanlun.mmd import _calc_decision_support_enhanced
from easy_tdx.chanlun.types import MMD, MMDType


def _seq(base: float, step: float, n: int) -> list[float]:
    return [base + step * i for i in range(n)]


class TestSimulateAdviceTrade:
    """单笔建议模拟测试。"""

    def test_stop_loss_triggered(self):
        """价格先跌破止损 → 以止损价出场（亏损单）。"""
        closes = [100, 100]
        highs = [101, 101]
        lows = [99, 95]  # 第二根跌破止损 97
        result = simulate_advice_trade(
            highs,
            lows,
            closes,
            entry_idx=0,
            entry_price=100.0,
            stop_loss=97.0,
            take_profit_1=104.0,
            max_hold=5,
        )
        assert result["exit_reason"] == "stop"
        assert result["exit_price"] == 97.0
        assert result["return_pct"] == -3.0

    def test_take_profit_triggered(self):
        """价格先达止盈 → 以止盈价出场（盈利单）。"""
        closes = [100, 100]
        highs = [101, 105]  # 第二根达到止盈 104
        lows = [99, 99]
        result = simulate_advice_trade(
            highs,
            lows,
            closes,
            entry_idx=0,
            entry_price=100.0,
            stop_loss=97.0,
            take_profit_1=104.0,
            max_hold=5,
        )
        assert result["exit_reason"] == "tp1"
        assert result["exit_price"] == 104.0
        assert result["return_pct"] == 4.0

    def test_expire_settles_at_close(self):
        """到期未触发 → 按最后收盘价结算。"""
        closes = [100, 100, 100, 101, 102, 103]
        highs = [101, 101, 101, 102, 102, 103]
        lows = [99, 99, 99, 99, 99, 99]
        result = simulate_advice_trade(
            highs,
            lows,
            closes,
            entry_idx=0,
            entry_price=100.0,
            stop_loss=97.0,
            take_profit_1=110.0,
            max_hold=5,
        )
        assert result["exit_reason"] == "expire"
        # 入场后第 5 根（索引 5）收盘 103
        assert result["exit_price"] == closes[5]
        assert result["return_pct"] == 3.0

    def test_same_bar_stop_wins(self):
        """同一根 K 线既触止损又触止盈 → 止损优先（保守）。"""
        closes = [100, 100]
        highs = [101, 105]  # 收高于 104
        lows = [99, 96]  # 但也跌破 97
        result = simulate_advice_trade(
            highs,
            lows,
            closes,
            entry_idx=0,
            entry_price=100.0,
            stop_loss=97.0,
            take_profit_1=104.0,
            max_hold=5,
        )
        assert result["exit_reason"] == "stop"

    def test_short_stop_triggered(self):
        """卖出建议：价格上行突破止损（上方）→ 亏损单。"""
        closes = [100, 100]
        highs = [101, 104]  # 第二根突破上方止损 103
        lows = [99, 99]
        result = simulate_advice_trade(
            highs,
            lows,
            closes,
            entry_idx=0,
            entry_price=100.0,
            stop_loss=103.0,
            take_profit_1=96.0,
            max_hold=5,
            direction="short",
        )
        assert result["exit_reason"] == "stop"
        assert result["exit_price"] == 103.0
        assert result["return_pct"] == -3.0

    def test_short_take_profit_triggered(self):
        """卖出建议：价格下行达止盈（下方）→ 盈利单。"""
        closes = [100, 100]
        highs = [101, 101]
        lows = [99, 95]  # 第二根跌破下方止盈 96
        result = simulate_advice_trade(
            highs,
            lows,
            closes,
            entry_idx=0,
            entry_price=100.0,
            stop_loss=103.0,
            take_profit_1=96.0,
            max_hold=5,
            direction="short",
        )
        assert result["exit_reason"] == "tp1"
        assert result["exit_price"] == 96.0
        assert result["return_pct"] == 4.0

    def test_short_invalid_shape(self):
        """卖出建议止损低于止盈 → 无效。"""
        result = simulate_advice_trade(
            [101, 101],
            [99, 99],
            [100, 100],
            entry_idx=0,
            entry_price=100.0,
            stop_loss=96.0,
            take_profit_1=103.0,
            max_hold=5,
            direction="short",
        )
        assert result["exit_reason"] == "invalid"

    def test_invalid_advice_shape(self):
        """止损不低于止盈的建议视为无效。"""
        result = simulate_advice_trade(
            [101, 101],
            [99, 99],
            [100, 100],
            entry_idx=0,
            entry_price=100.0,
            stop_loss=105.0,
            take_profit_1=95.0,
            max_hold=5,
        )
        assert result["exit_reason"] == "invalid"

    def test_out_of_range_entry(self):
        """入场索引越界返回 invalid。"""
        result = simulate_advice_trade(
            [101],
            [99],
            [100],
            entry_idx=5,
            entry_price=100.0,
            stop_loss=97.0,
            take_profit_1=104.0,
            max_hold=5,
        )
        assert result["exit_reason"] == "invalid"


class TestSimulateAdviceBatch:
    """批量建议聚合测试。"""

    def test_batch_statistics_structure(self):
        """批量结果包含必要统计字段。"""
        highs = _seq(100, 0.5, 30)
        lows = _seq(99, 0.4, 30)
        closes = _seq(100, 0.5, 30)
        advices = [
            {
                "entry_idx": 0,
                "entry_price": 100.0,
                "stop_loss": 97.0,
                "take_profit_1": 106.0,
                "max_hold": 5,
            },
            {
                "entry_idx": 5,
                "entry_price": 102.5,
                "stop_loss": 99.5,
                "take_profit_1": 108.0,
                "max_hold": 5,
            },
            {
                "entry_idx": 10,
                "entry_price": 105.0,
                "stop_loss": 102.0,
                "take_profit_1": 111.0,
                "max_hold": 5,
            },
        ]
        result = simulate_advice_batch(highs, lows, closes, advices)
        assert result["count"] == 3
        assert 0.0 <= result["win_rate"] <= 1.0
        for key in ("avg_return", "total_return", "stop_rate", "tp_rate", "expire_rate"):
            assert key in result

    def test_invalid_advices_skipped(self):
        """非法建议在批量中被过滤。"""
        highs = _seq(100, 0.5, 10)
        lows = _seq(99, 0.4, 10)
        closes = _seq(100, 0.5, 10)
        advices = [
            {"entry_idx": 0, "entry_price": 100.0, "stop_loss": 97.0, "take_profit_1": 106.0},
            {
                "entry_idx": -1,
                "entry_price": 100.0,
                "stop_loss": 97.0,
                "take_profit_1": 106.0,
            },  # 非法索引
            {
                "entry_idx": 0,
                "entry_price": 0.0,
                "stop_loss": 97.0,
                "take_profit_1": 106.0,
            },  # 非法价格
        ]
        result = simulate_advice_batch(highs, lows, closes, advices)
        assert result["count"] == 1


class TestV102AdviceEndToEnd:
    """用 V102 条件266 生成的 3买 建议跑模拟器。"""

    def test_buy3_advice_replayable(self):
        """BUY_3 生成的入场/止损/止盈建议可在历史序列上回放。"""
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买测试")
        mmd.bi = MagicMock()
        mmd.bi.low = 98.0
        mmd.bi.high = 102.0
        mmd.zs = MagicMock()
        mmd.zs.zg = 105.0
        mmd.zs.zd = 95.0
        closes = [100.0] * 30
        highs = [101.0] * 30
        lows = [99.0] * 30

        advice = _calc_decision_support_enhanced(mmd, closes, highs, lows, None, None)

        assert advice["entry_price"] > 0
        assert advice["stop_loss"] < advice["entry_price"] < advice["take_profit_1"]

        result = simulate_advice_trade(
            closes,
            highs,
            lows,
            entry_idx=10,
            entry_price=advice["entry_price"],
            stop_loss=advice["stop_loss"],
            take_profit_1=advice["take_profit_1"],
            max_hold=10,
        )
        # 亏损单不低于理论最大亏损（止损位），盈利单不高于理论最大盈利（止盈位）
        assert (
            result["return_pct"]
            >= (advice["stop_loss"] - advice["entry_price"]) / advice["entry_price"] * 100 - 0.01
        )
        assert (
            result["return_pct"]
            <= (advice["take_profit_1"] - advice["entry_price"]) / advice["entry_price"] * 100
            + 0.01
        )

    def test_batch_with_v102_advices(self):
        """多笔 V102 建议批量回放输出统计。"""
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买测试")
        mmd.bi = MagicMock()
        mmd.bi.low = 98.0
        mmd.bi.high = 102.0
        mmd.zs = MagicMock()
        mmd.zs.zg = 105.0
        mmd.zs.zd = 95.0
        closes = [100.0] * 40
        highs = [101.0] * 40
        lows = [99.0] * 40

        advices = []
        for idx in (5, 15, 25):
            a = _calc_decision_support_enhanced(mmd, closes, highs, lows, None, None)
            advices.append(
                {
                    "entry_idx": idx,
                    "entry_price": a["entry_price"],
                    "stop_loss": a["stop_loss"],
                    "take_profit_1": a["take_profit_1"],
                    "max_hold": 8,
                }
            )

        result = simulate_advice_batch(closes, highs, lows, advices)
        assert result["count"] == 3
        assert result["avg_return"] != 0.0 or result["expire_rate"] > 0
