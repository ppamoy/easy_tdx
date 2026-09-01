"""组合级准确度聚合（V99）的单元测试。"""

from __future__ import annotations

import pandas as pd
import pytest

from easy_tdx.backtest.signal_accuracy import (
    _symbol_accuracy_row,
    aggregate_portfolio_accuracy,
)


def _result_dict(
    total_return: float,
    win_rate: float,
    sharpe: float,
    trades: int,
    hit_rate: float | None,
    baseline_hit: float | None = 0.5,
) -> dict:
    """构造与 BacktestResult.to_dict() 同构的字典。"""
    return {
        "performance": {
            "total_return": total_return,
            "win_rate": win_rate,
            "sharpe": sharpe,
            "max_drawdown": 0.05,
            "total_trades": trades,
        },
        "signal_accuracy": {
            "buy": {
                "horizons": {
                    "5": {
                        "count": 3,
                        "hit_rate": hit_rate,
                        "baseline_hit_rate": baseline_hit,
                    }
                }
            }
        },
    }


class TestSymbolAccuracyRow:
    def test_extracts_fields(self) -> None:
        row = _symbol_accuracy_row("SZ000001", _result_dict(0.12, 0.6, 1.2, 8, 0.67))
        assert row["symbol"] == "SZ000001"
        assert row["total_return"] == pytest.approx(0.12)
        assert row["win_rate"] == pytest.approx(0.6)
        assert row["trades"] == 8
        assert row["hit_rate"] == pytest.approx(0.67)
        assert row["excess_hit_rate"] == pytest.approx(0.17)

    def test_missing_accuracy(self) -> None:
        row = _symbol_accuracy_row("SZ000001", {"performance": {"total_return": 0.1}})
        assert row["hit_rate"] is None
        assert row["excess_hit_rate"] is None


class TestAggregatePortfolioAccuracy:
    def test_empty(self) -> None:
        rep = aggregate_portfolio_accuracy({})
        assert rep["symbols"] == []
        assert "无标的" in rep["verdict"]

    def test_rows_carry_trust_fields(self) -> None:
        """V110: 每只标的的聚合行应带 trust_score/trust_grade。"""
        results = {
            "SZ000001": _result_dict(0.12, 0.6, 1.2, 8, 0.67),
            "SZ000002": _result_dict(0.05, 0.5, 0.8, 6, 0.55),
        }
        rep = aggregate_portfolio_accuracy(results, None)
        for row in rep["symbols"]:
            assert "trust_score" in row
            assert "trust_grade" in row
            assert row["trust_score"] is not None
            assert row["trust_grade"] in ("高", "中", "低")

    def test_aggregates_weighted(self) -> None:
        results = {
            "SZ000001": _result_dict(0.12, 0.6, 1.2, 8, 0.67),
            "SZ000002": _result_dict(-0.03, 0.4, 0.3, 5, 0.5),
        }
        allocs = {"SZ000001": 0.5, "SZ000002": 0.5}
        rep = aggregate_portfolio_accuracy(results, allocs)
        assert len(rep["symbols"]) == 2
        p = rep["portfolio"]
        assert p["symbols"] == 2
        assert p["symbols_with_accuracy"] == 2
        # 加权平均命中率 = (0.5*0.67 + 0.5*0.5) = 0.585
        assert p["avg_hit_rate"] == pytest.approx(0.585)
        assert p["avg_excess_hit_rate"] == pytest.approx(0.085)
        assert p["positive_symbols"] == 1
        assert p["hit_above_baseline"] == 1
        assert isinstance(rep["verdict"], str)
        assert len(rep["verdict"]) > 0

    def test_verdict_flags_poor_timing(self) -> None:
        # 两只命中率都低于随机基准
        results = {
            "SZ000001": _result_dict(0.05, 0.5, 0.8, 6, 0.4, 0.5),
            "SZ000002": _result_dict(0.03, 0.5, 0.7, 5, 0.45, 0.5),
        }
        rep = aggregate_portfolio_accuracy(results, None)
        assert rep["portfolio"]["hit_above_baseline"] == 0
        assert "不高于随机基准" in rep["verdict"]

    def test_handles_backtest_result_objects(self) -> None:
        # 传入真正的 BacktestResult 对象也应可用
        from easy_tdx.backtest.engine import BacktestEngine
        from easy_tdx.backtest.strategy import Strategy

        class BuyOnce(Strategy):
            def init(self) -> None:
                pass

            def next(self) -> None:
                if self._bar_index == 5:
                    self.buy(size=0)
                elif self._bar_index == 15:
                    self.sell(size=0)

        n = 40
        closes = [100 + i * 0.5 for i in range(n)]
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-01", periods=n, freq="D"),
                "open": [c - 0.2 for c in closes],
                "high": [c + 0.3 for c in closes],
                "low": [c - 0.3 for c in closes],
                "close": closes,
                "vol": [1_000_000] * n,
                "amount": [1_000_000.0] * n,
            }
        )
        engine = BacktestEngine(BuyOnce, cash=100000)
        result = engine.run(df)
        rep = aggregate_portfolio_accuracy({"TEST": result}, {"TEST": 1.0})
        assert rep["portfolio"]["symbols"] == 1
        assert rep["symbols"][0]["symbol"] == "TEST"
