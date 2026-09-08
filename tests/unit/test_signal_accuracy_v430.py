"""backtest/signal_accuracy.py V430 盈亏比 测试。"""

from __future__ import annotations

import numpy as np

from easy_tdx.backtest.signal_accuracy import (
    _build_type_summary,
    _profit_factor,
    _signal_type_verdict,
    compute_signal_accuracy_by_type,
)


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


class TestSignalTypeVerdict:
    def test_significant_above_with_good_pf(self) -> None:
        report = {
            "direction": "BUY",
            "horizons": {
                "5": {"count": 20, "excess_hit_rate": 0.10, "profit_factor": 2.0},
            },
        }
        v = _signal_type_verdict(report)
        assert "显著优于随机" in v
        assert "盈亏比差" not in v

    def test_significant_above_with_bad_pf(self) -> None:
        report = {
            "direction": "BUY",
            "horizons": {
                "5": {"count": 20, "excess_hit_rate": 0.10, "profit_factor": 0.6},
            },
        }
        v = _signal_type_verdict(report)
        assert "显著优于随机" in v
        assert "盈亏比差" in v

    def test_insufficient_sample(self) -> None:
        report = {"direction": "BUY", "horizons": {}}
        assert _signal_type_verdict(report) == "样本不足，无法可靠评估"


class TestBuildTypeSummary:
    def test_summary_includes_profit_factor(self) -> None:
        """V456: 最强买点/卖点文案附盈亏比。"""
        by_type = {
            "3buy": {
                "type": "3buy",
                "direction": "BUY",
                "horizons": {
                    "5": {
                        "count": 20,
                        "hit_rate": 0.7,
                        "excess_hit_rate": 0.15,
                        "profit_factor": 2.5,
                    },
                },
            },
        }
        s = _build_type_summary(by_type)
        assert "最强买点 3buy" in s
        assert "盈亏比 2.50" in s

    def test_summary_no_pf_when_zero(self) -> None:
        by_type = {
            "1sell": {
                "type": "1sell",
                "direction": "SELL",
                "horizons": {
                    "5": {
                        "count": 10,
                        "hit_rate": 0.4,
                        "excess_hit_rate": -0.05,
                        "profit_factor": 0.0,
                    },
                },
            },
        }
        s = _build_type_summary(by_type)
        assert "最强卖点 1sell" in s
        assert "盈亏比" not in s
