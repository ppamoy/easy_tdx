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
    def test_verify_walk_forward_option(self):
        """V225: verify 应暴露 --walk-forward 选项。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["verify", "--help"])
        assert result.exit_code == 0
        assert "--walk-forward" in result.output
        assert "--step-ratio" in result.output
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

    def test_verify_portfolio_only_robust(self):
        """V241: verify-portfolio 应暴露 --only-robust；未开 --out-of-sample 时报错。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        help_result = runner.invoke(cli, ["verify-portfolio", "--help"])
        assert help_result.exit_code == 0
        assert "--only-robust" in help_result.output
        # --only-robust 必须与 --out-of-sample 同时使用
        bad = runner.invoke(cli, ["verify-portfolio", "SZ 000001", "--only-robust"])
        assert bad.exit_code == 1
        assert "需要同时使用 --out-of-sample" in bad.output
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

    def test_verify_multi_walk_forward_option(self):
        """V243: verify-multi 应暴露 --walk-forward/--step-ratio 选项。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["verify-multi", "--help"])
        assert result.exit_code == 0
        assert "--walk-forward" in result.output
        assert "--step-ratio" in result.output
    def test_reverify_help(self):
        """V213: reverify 命令应注册且 --help 正常。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["reverify", "--help"])
        assert result.exit_code == 0
        assert "一键重验" in result.output or "重验" in result.output
        assert "--ids" in result.output

    def test_reverify_walk_forward_option(self):
        """V245: reverify 应暴露 --walk-forward 选项。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["reverify", "--help"])
        assert result.exit_code == 0
        assert "--walk-forward" in result.output
        assert "--step-ratio" in result.output
    def test_run_all_walk_forward_option(self):
        """V233: run-all 应暴露 --walk-forward/--step-ratio 选项，且 helper 能产出报告。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["run-all", "--help"])
        assert result.exit_code == 0
        assert "--walk-forward" in result.output
        assert "--step-ratio" in result.output

        # helper：150 根合成数据 → 返回 walk-forward 报告结构
        from datetime import datetime, timedelta

        import numpy as np
        import pandas as pd

        from easy_tdx.backtest import Strategy, crossover
        from easy_tdx.cli.cmd_run_all import _compute_walk_forward_single

        def _ma(x, n):
            return pd.Series(x).rolling(n).mean().to_numpy()

        class _WfStrat(Strategy):
            def init(self) -> None:
                self.ma5 = self.I(lambda x: _ma(x, 5), self.data.close)
                self.ma20 = self.I(lambda x: _ma(x, 20), self.data.close)
                self.cross = crossover(self.ma5, self.ma20)

            def next(self) -> None:
                if self.cross[self._bar_index] and self.position["size"] == 0:
                    self.buy(size=0)
                elif self.position["size"] > 0:
                    self.sell(size=0)

        n = 150
        base = datetime(2023, 1, 1)
        close = np.linspace(100.0, 120.0, n)
        df = pd.DataFrame({
            "datetime": [base + timedelta(days=i) for i in range(n)],
            "open": close - 0.1, "high": close + 0.2, "low": close - 0.2,
            "close": close, "vol": np.full(n, 1_000_000.0),
        })
        report = _compute_walk_forward_single(df, _WfStrat, cash=1000000, commission=0.0003)
        assert report is not None
        assert report["windows"] >= 1
        assert "train_mean" in report and "test_mean" in report
        assert "positive_test_windows" in report and "verdict" in report
        assert "degraded" in report

    def test_screen_rank_verification_columns(self):
        """V279: screen rank 应暴露 --out-of-sample，且 RankEntry 验证字段可序列化。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        help_result = runner.invoke(cli, ["screen", "rank", "--help"])
        assert help_result.exit_code == 0
        assert "--out-of-sample" in help_result.output

        from easy_tdx.screen.ranker import RankEntry, SignalRanker

        entry = RankEntry(
            rank=1, code="000001", market="SZ", name="平安银行",
            signal_date=20240101, last_close=10.0,
            performance={"total_return": 0.1, "sharpe": 1.2},
            accuracy={"hit_rate": 0.65, "excess_hit_rate": 0.1},
            trust={"score": 80, "grade": "高", "verdict": "高可信度"},
            oos={"degraded": False, "verdict": "✅ 样本外稳健"},
        )
        json_str = SignalRanker.to_json([entry], "TestStrategy", "sharpe")
        assert '"accuracy"' in json_str
        assert '"trust"' in json_str
        assert '"oos"' in json_str
        assert '"hit_rate"' in json_str and '"score"' in json_str

        table = SignalRanker.to_table([entry], "sharpe")
        assert "5根命中" in table
        assert "可信度" in table
        assert "样本外" in table

    def test_backtest_walk_forward_request(self):
        """V287: BacktestRequest 应支持 use_walk_forward，且 _run_backtest 返回 walk_forward。"""
        from datetime import datetime, timedelta

        import numpy as np
        import pandas as pd

        from easy_tdx.web.backtest_schemas import BacktestRequest
        from easy_tdx.web.routers.backtest import _run_backtest

        n = 220
        base = datetime(2023, 1, 1)
        close = np.linspace(100.0, 120.0, n)
        df = pd.DataFrame({
            "datetime": [base + timedelta(days=i) for i in range(n)],
            "open": close - 0.1, "high": close + 0.2, "low": close - 0.2,
            "close": close, "vol": np.full(n, 1_000_000.0),
            "amount": np.full(n, 1_000_000_000.0),
        })
        ohlcv = df.to_dict(orient="records")
        req = BacktestRequest(
            strategy="ma_cross", params={"fast": 5, "slow": 20},
            cash=500000, use_walk_forward=True, step_ratio=0.1, ohlcv=ohlcv,
        )
        assert req.use_walk_forward is True
        assert req.step_ratio == 0.1
        result = _run_backtest(df, req)
        wf = result.get("walk_forward")
        assert wf is not None
        assert wf.get("windows", 0) >= 1
        assert "verdict" in wf
        # 不开启时不计算
        req2 = BacktestRequest(
            strategy="ma_cross", params={"fast": 5, "slow": 20},
            cash=500000, ohlcv=ohlcv,
        )
        result2 = _run_backtest(df, req2)
        assert result2.get("walk_forward") is None

    def test_verify_multi_table_option(self):
        """V293: verify-multi 应暴露 --table 选项。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["verify-multi", "--help"])
        assert result.exit_code == 0
        assert "--table" in result.output

    def test_verify_table_option(self):
        """V307: verify（单标）应暴露 --table 选项。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["verify", "--help"])
        assert result.exit_code == 0
        assert "--table" in result.output

    def test_verify_portfolio_walk_forward_option(self):
        """V297: verify-portfolio 应暴露 --walk-forward/--step-ratio 选项。"""
        from easy_tdx.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["verify-portfolio", "--help"])
        assert result.exit_code == 0
        assert "--walk-forward" in result.output
        assert "--step-ratio" in result.output
