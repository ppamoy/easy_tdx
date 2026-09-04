"""backtest/cli.py 表格输出纯函数测试（V398）。

覆盖 _print_table / _print_portfolio_table 的渲染分支，用 MagicMock 构造
回测结果对象，monkeypatch click.echo 捕获输出。不触网。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import click
import pandas as pd

from easy_tdx.backtest.cli import _print_portfolio_table, _print_table


def _run(fn, arg, monkeypatch) -> list[str]:
    lines: list[str] = []

    def _echo(s: str = "") -> None:
        lines.append(str(s))

    monkeypatch.setattr(click, "echo", _echo)
    fn(arg)
    return lines


class TestPrintTable:
    def test_no_trades(self, monkeypatch) -> None:
        result = MagicMock()
        result.performance = {
            "total_return": 0.1,
            "annual_return": 0.2,
            "max_drawdown": 0.05,
            "sharpe": 1.0,
            "win_rate": 0.5,
            "total_trades": 0,
        }
        result.config = {
            "cash": 100000.0,
            "commission": 0.0003,
            "execution": "next_open",
            "chanlun_level": "DAILY",
        }
        result.diagnostic = "样本不足"
        result.trades = pd.DataFrame()
        text = "\n".join(_run(_print_table, result, monkeypatch))
        assert "回测绩效概要" in text
        assert "无交易记录" in text
        assert "缠论级别" in text

    def test_with_trades(self, monkeypatch) -> None:
        result = MagicMock()
        result.performance = {"total_return": 0.1, "total_trades": 1}
        result.config = {"cash": 100000.0, "commission": 0.0003, "execution": "next_open"}
        result.diagnostic = None
        result.trades = pd.DataFrame(
            [
                {
                    "datetime": "2024-01-01",
                    "direction": "BUY",
                    "rejected": False,
                    "size": 100,
                    "price": 10.0,
                    "pnl": 0.0,
                }
            ]
        )
        text = "\n".join(_run(_print_table, result, monkeypatch))
        assert "最近交易记录" in text
        assert "买入" in text


class TestPrintPortfolioTable:
    def test_rows(self, monkeypatch) -> None:
        result = MagicMock()
        result.total_performance = {
            "total_stocks": 1,
            "total_cash": 100000.0,
            "total_return": 0.1,
            "annual_return": 0.2,
        }
        stock = MagicMock()
        stock.performance = {
            "total_return": 0.1,
            "sharpe": 1.0,
            "max_drawdown": 0.05,
            "total_trades": 5,
        }
        result.individual_results = {"SZ000001": stock}
        result.equity_allocation = {"SZ000001": 1.0}
        text = "\n".join(_run(_print_portfolio_table, result, monkeypatch))
        assert "组合回测绩效概要" in text
        assert "SZ000001" in text
