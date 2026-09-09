"""backtest/performance.py 纯函数测试（V477）。"""

from __future__ import annotations

import numpy as np

from easy_tdx.backtest.performance import PerformanceAnalyzer


class TestMaxConsecutiveTrades:
    def test_max_positive_streak(self) -> None:
        pnl = np.array([1.0, 2.0, -1.0, 3.0, 4.0, 5.0, -2.0])
        assert PerformanceAnalyzer._compute_max_consecutive_trades(pnl, True) == 3

    def test_max_negative_streak(self) -> None:
        pnl = np.array([-1.0, -2.0, 3.0, -4.0, -5.0, -6.0, -7.0])
        assert PerformanceAnalyzer._compute_max_consecutive_trades(pnl, False) == 4

    def test_empty_series(self) -> None:
        assert PerformanceAnalyzer._compute_max_consecutive_trades(np.array([]), True) == 0

    def test_zero_breaks_streak(self) -> None:
        # 0 盈亏算亏损（<=0），连续正收益被 0 打断
        pnl = np.array([1.0, 0.0, 2.0])
        assert PerformanceAnalyzer._compute_max_consecutive_trades(pnl, True) == 1
