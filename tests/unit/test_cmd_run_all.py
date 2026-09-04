"""cli/cmd_run_all.py 纯函数边界测试（V399）。

覆盖 _map_trade_values / _print_ranking / _load_strategy_class 三个纯函数，
不触网、不加载真实策略文件。
"""

from __future__ import annotations

import click
import pandas as pd

from easy_tdx.cli.cmd_run_all import _map_trade_values, _print_ranking


class TestMapTradeValues:
    def test_maps_dates(self) -> None:
        trades = pd.DataFrame({"datetime": pd.date_range("2024-01-03", periods=2, freq="D")})
        equity = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-01", periods=5, freq="D"),
                "total": [100.0, 200.0, 300.0, 400.0, 500.0],
            }
        )
        vals = _map_trade_values(trades, equity, initial_cash=100.0)
        assert vals == [3.0, 4.0]

    def test_clamps_out_of_range(self) -> None:
        trades = pd.DataFrame(
            {"datetime": [pd.Timestamp("2020-01-01"), pd.Timestamp("2030-01-01")]}
        )
        equity = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-01", periods=2, freq="D"),
                "total": [100.0, 200.0],
            }
        )
        vals = _map_trade_values(trades, equity, initial_cash=100.0)
        assert vals == [1.0, 2.0]


class TestPrintRanking:
    def _run(self, results, backtest_results, monkeypatch):
        lines: list[str] = []

        def echo(s: str = "") -> None:
            lines.append(str(s))

        monkeypatch.setattr(click, "echo", echo)
        ok = _print_ranking(results, backtest_results)
        return ok, lines

    def test_all_failed(self, monkeypatch) -> None:
        ok, lines = self._run([{"strategy": "a", "error": "boom"}], {}, monkeypatch)
        assert ok is False
        assert "所有策略均运行失败！" in lines
