"""backtest/signal_accuracy.py V430 盈亏比 测试。"""

from __future__ import annotations

import numpy as np

from easy_tdx.backtest.signal_accuracy import _profit_factor, compute_signal_accuracy_by_type


class TestProfitFactor:
    def test_normal(self) -> None:
        # 平均盈利 (0.1+0.15)/2=0.125，平均亏损 0.05 → PF=2.5
        fwd = np.array([0.1, 0.15, -0.05, -0.05], dtype=float)
        assert _profit_factor(fwd) == 2.5

    def test_only_gains(self) -> None:
        assert _profit_factor(np.array([0.1, 0.2])) == 999.0

    def test_only_losses(self) -> None:
        assert _profit_factor(np.array([-0.1, -0.2])) == 0.0

    def test_empty(self) -> None:
        assert _profit_factor(np.array([], dtype=float)) == 0.0


class TestTypeAccuracyProfitFactor:
    def test_by_type_includes_profit_factor(self) -> None:
        closes = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
        signals = [{"type": "3buy", "bar_index": 0}, {"type": "3buy", "bar_index": 1}]
        report = compute_signal_accuracy_by_type(closes, signals)
        assert "3buy" in report["by_type"]
        h = report["by_type"]["3buy"]["horizons"]
        assert "profit_factor" in h["3"] or "profit_factor" in h["5"]
