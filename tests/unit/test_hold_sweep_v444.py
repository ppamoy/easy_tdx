"""backtest/advice_simulator.py V444 多持有期敏感性 测试。"""

from __future__ import annotations

from easy_tdx.backtest.advice_simulator import simulate_advice_hold_sweep


class TestHoldSweep:
    def test_sweep_returns_each_hold(self) -> None:
        highs = [100.0, 105.0, 106.0, 104.0, 103.0, 102.0, 101.0, 100.0, 99.0, 98.0]
        lows = [99.0, 100.0, 101.0, 102.0, 101.0, 100.0, 99.0, 98.0, 97.0, 96.0]
        closes = [100.0, 104.0, 105.0, 103.0, 102.0, 101.0, 100.0, 99.0, 98.0, 97.0]
        advices = [
            {
                "entry_idx": 0,
                "entry_price": 100.0,
                "stop_loss": 97.0,
                "take_profit_1": 106.0,
                "max_hold": 5,
            },
        ]
        result = simulate_advice_hold_sweep(highs, lows, closes, advices, holds=(3, 5))
        assert "3" in result
        assert "5" in result
        assert result["3"]["count"] == 1
        assert result["5"]["count"] == 1

    def test_sweep_differs_by_hold(self) -> None:
        """不同持有期可得到不同的到期结算收益。"""
        highs = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]
        lows = [99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0]
        closes = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]
        advices = [
            {
                "entry_idx": 0,
                "entry_price": 100.0,
                "stop_loss": 98.0,
                "take_profit_1": 103.0,
                "max_hold": 10,
            },
        ]
        result = simulate_advice_hold_sweep(highs, lows, closes, advices, holds=(2, 10))
        assert result["2"]["trades"][0]["exit_reason"] == "expire"
        # 持有 10 根时第 3 根 high=103 触发止盈
        assert result["10"]["trades"][0]["exit_reason"] == "tp1"
        assert result["2"]["trades"][0]["return_pct"] != result["10"]["trades"][0]["return_pct"]
