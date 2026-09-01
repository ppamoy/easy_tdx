"""回测 CLI 命令测试。"""

from __future__ import annotations

from click.testing import CliRunner


class TestVerifyCLI:
    """V117: 模型验证报告命令。"""

    def test_help(self):
        """测试 verify --help。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["verify", "--help"])
        assert result.exit_code == 0
        assert "模型验证" in result.output
        assert "--strategy" in result.output
        assert "--out-of-sample" in result.output

    def test_bad_params_json(self):
        """非法的 --params JSON 应报错退出。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["verify", "SZ", "000001", "--params", "{oops"])
        assert result.exit_code == 1
        assert "不是合法 JSON" in result.output

    def test_verify_multi_help(self):
        """V119: verify-multi --help。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["verify-multi", "--help"])
        assert result.exit_code == 0
        assert "批量模型验证" in result.output
        assert "--strategy" in result.output

    def test_verify_multi_bad_params(self):
        """V119: verify-multi 非 JSON params 报错。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["verify-multi", "SZ 000001", "--params", "{oops"])
        assert result.exit_code == 1
        assert "不是合法 JSON" in result.output

    def test_verify_multi_validation_options(self):
        """V132: verify-multi 应暴露 --segments / --out-of-sample / --train-ratio。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["verify-multi", "--help"])
        assert result.exit_code == 0
        assert "--segments" in result.output
        assert "--out-of-sample" in result.output
        assert "--train-ratio" in result.output


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
    def test_print_ranking_with_robust_oos_columns(self):
        """V155: 排名表应显示稳健性/样本外列且不崩溃。"""
        from unittest.mock import patch

        import pandas as pd

        from easy_tdx.cli.cmd_run_all import _print_ranking

        class _FakeBT:
            performance = {"total_return": 0.2}
            config = {"cash": 100000, "commission": 0.0003, "execution": "next_open"}
            trades = pd.DataFrame(
                columns=["datetime", "direction", "size", "price", "pnl", "rejected"]
            )
            equity_curve = pd.DataFrame()

        base = {
            "strategy": "ma_cross",
            "total_return": 0.2, "annual_return": 0.2, "max_drawdown": 0.1,
            "sharpe": 1.2, "sortino": 1.1, "calmar": 2.0, "win_rate": 0.6,
            "total_trades": 10, "profit_factor": 1.5, "volatility": 0.2,
        }
        results = [
            {**base, "strategy": "a", "overfit_likely": False, "oos_degraded": False},
            {**base, "strategy": "b", "overfit_likely": True, "oos_degraded": True},
        ]
        backtest_results = {"a": _FakeBT()}

        with patch("easy_tdx.cli.cmd_run_all.click.echo") as echo:
            ok = _print_ranking(results, backtest_results)  # type: ignore[arg-type]
            assert ok is True
            echoed = "".join(c[0][0] if c and c[0] else "" for c in echo.call_args_list)
            assert "稳健性" in echoed
            assert "样本外" in echoed
            assert "✅稳健" in echoed
            assert "⚠过拟合" in echoed
            assert "✅泛化" in echoed
            assert "⚠衰减" in echoed
    def test_verify_output_file_option(self):
        """V172: verify / verify-multi 应暴露 --output-file 选项。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        r1 = runner.invoke(cli, ["verify", "--help"])
        assert r1.exit_code == 0
        assert "--output-file" in r1.output
        r2 = runner.invoke(cli, ["verify-multi", "--help"])
        assert r2.exit_code == 0
        assert "--output-file" in r2.output
    def test_run_all_output_file_option(self):
        """V174: run-all 应暴露 --output-file 选项。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["run-all", "--help"])
        assert result.exit_code == 0
        assert "--output-file" in result.output

    def test_verify_portfolio_help(self):
        """V176: verify-portfolio --help。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["verify-portfolio", "--help"])
        assert result.exit_code == 0
        assert "组合模型验证" in result.output
        assert "--out-of-sample" in result.output

    def test_verify_portfolio_bad_params(self):
        """V176: verify-portfolio 非 JSON params 报错。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["verify-portfolio", "SZ 000001", "--params", "{oops"])
        assert result.exit_code == 1
        assert "不是合法 JSON" in result.output
    def test_verify_multi_only_robust(self):
        """V199: verify-multi 应暴露 --only-robust；未开 --out-of-sample 时报错。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        help_result = runner.invoke(cli, ["verify-multi", "--help"])
        assert help_result.exit_code == 0
        assert "--only-robust" in help_result.output
        # --only-robust 必须与 --out-of-sample 同时使用
        bad = runner.invoke(cli, ["verify-multi", "SZ 000001", "--only-robust"])
        assert bad.exit_code == 1
        assert "需要同时使用 --out-of-sample" in bad.output
    def test_run_all_only_robust_option(self):
        """V201: run-all 应暴露 --only-robust 选项。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["run-all", "--help"])
        assert result.exit_code == 0
        assert "--only-robust" in result.output
