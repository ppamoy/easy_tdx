"""回测 CLI 命令测试。"""

from __future__ import annotations

from click.testing import CliRunner


class TestBacktestCLI:
    """测试回测 CLI 命令。"""

    def test_help(self):
        """测试 --help 显示帮助。"""
        from easy_tdx.backtest.cli import backtest

        runner = CliRunner()
        result = runner.invoke(backtest, ["--help"])
        assert result.exit_code == 0
        assert "回测引擎" in result.output
        assert "--strategy-file" in result.output
        assert "--cash" in result.output
        assert "--commission" in result.output

    def test_missing_strategy_fails(self):
        """测试不指定策略则失败。"""
        from easy_tdx.backtest.cli import backtest

        runner = CliRunner()
        result = runner.invoke(backtest, ["SZ", "000001"])
        assert result.exit_code == 1
        assert "必须指定" in result.output or "错误" in result.output

    def test_print_ranking_with_accuracy_columns(self):
        """V115: 排名表应显示准确度/可信度列且不崩溃。"""
        from unittest.mock import patch

        import pandas as pd

        from easy_tdx.cli.cmd_run_all import _print_ranking

        # 伪造一个带 signal_accuracy/model_trust 的最小 BacktestResult 用于 BEST 明细
        class _FakeBT:
            performance = {"total_return": 0.2}
            config = {"cash": 100000, "commission": 0.0003, "execution": "next_open"}
            trades = pd.DataFrame(
                columns=["datetime", "direction", "size", "price", "pnl", "rejected"]
            )
            equity_curve = pd.DataFrame()

        results = [
            {
                "strategy": "ma_cross",
                "total_return": 0.2,
                "annual_return": 0.2,
                "max_drawdown": 0.1,
                "sharpe": 1.2,
                "sortino": 1.1,
                "calmar": 2.0,
                "win_rate": 0.6,
                "total_trades": 10,
                "profit_factor": 1.5,
                "volatility": 0.2,
                "hit_rate": 0.65,
                "excess_hit_rate": 0.15,
                "trust_score": 78.0,
                "trust_grade": "高",
            },
            {
                "strategy": "macd",
                "total_return": -0.05,
                "annual_return": -0.05,
                "max_drawdown": 0.15,
                "sharpe": 0.5,
                "sortino": 0.4,
                "calmar": 0.0,
                "win_rate": 0.45,
                "total_trades": 5,
                "profit_factor": 0.9,
                "volatility": 0.15,
                "hit_rate": 0.5,
                "excess_hit_rate": -0.05,
                "trust_score": 40.0,
                "trust_grade": "低",
            },
        ]
        backtest_results = {"ma_cross": _FakeBT()}

        with patch("easy_tdx.cli.cmd_run_all.click.echo") as echo:
            ok = _print_ranking(results, backtest_results)  # type: ignore[arg-type]
            assert ok is True
            echoed = "".join(c[0][0] if c and c[0] else "" for c in echo.call_args_list)
            assert "可信度" in echoed
            # 两行策略都应出现在输出中
            assert "ma_cross" in echoed
            assert "macd" in echoed
