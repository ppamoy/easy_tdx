"""V102 决策支持建议执行模拟器测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

from easy_tdx.backtest.advice_simulator import simulate_advice_batch, simulate_advice_trade
from easy_tdx.chanlun.mmd import _calc_decision_support_enhanced
from easy_tdx.chanlun.types import MMD, MMDType


def _seq(base: float, step: float, n: int) -> list[float]:
    return [base + step * i for i in range(n)]


class TestSimulateAdviceTrade:
    """单笔建议模拟测试。"""

    def test_stop_loss_triggered(self):
        """价格先跌破止损 → 以止损价出场（亏损单）。"""
        closes = [100, 100]
        highs = [101, 101]
        lows = [99, 95]  # 第二根跌破止损 97
        result = simulate_advice_trade(
            highs,
            lows,
            closes,
            entry_idx=0,
            entry_price=100.0,
            stop_loss=97.0,
            take_profit_1=104.0,
            max_hold=5,
        )
        assert result["exit_reason"] == "stop"
        assert result["exit_price"] == 97.0
        assert result["return_pct"] == -3.0

    def test_take_profit_triggered(self):
        """价格先达止盈 → 以止盈价出场（盈利单）。"""
        closes = [100, 100]
        highs = [101, 105]  # 第二根达到止盈 104
        lows = [99, 99]
        result = simulate_advice_trade(
            highs,
            lows,
            closes,
            entry_idx=0,
            entry_price=100.0,
            stop_loss=97.0,
            take_profit_1=104.0,
            max_hold=5,
        )
        assert result["exit_reason"] == "tp1"
        assert result["exit_price"] == 104.0
        assert result["return_pct"] == 4.0

    def test_expire_settles_at_close(self):
        """到期未触发 → 按最后收盘价结算。"""
        closes = [100, 100, 100, 101, 102, 103]
        highs = [101, 101, 101, 102, 102, 103]
        lows = [99, 99, 99, 99, 99, 99]
        result = simulate_advice_trade(
            highs,
            lows,
            closes,
            entry_idx=0,
            entry_price=100.0,
            stop_loss=97.0,
            take_profit_1=110.0,
            max_hold=5,
        )
        assert result["exit_reason"] == "expire"
        # 入场后第 5 根（索引 5）收盘 103
        assert result["exit_price"] == closes[5]
        assert result["return_pct"] == 3.0

    def test_same_bar_stop_wins(self):
        """同一根 K 线既触止损又触止盈 → 止损优先（保守）。"""
        closes = [100, 100]
        highs = [101, 105]  # 收高于 104
        lows = [99, 96]  # 但也跌破 97
        result = simulate_advice_trade(
            highs,
            lows,
            closes,
            entry_idx=0,
            entry_price=100.0,
            stop_loss=97.0,
            take_profit_1=104.0,
            max_hold=5,
        )
        assert result["exit_reason"] == "stop"

    def test_short_stop_triggered(self):
        """卖出建议：价格上行突破止损（上方）→ 亏损单。"""
        closes = [100, 100]
        highs = [101, 104]  # 第二根突破上方止损 103
        lows = [99, 99]
        result = simulate_advice_trade(
            highs,
            lows,
            closes,
            entry_idx=0,
            entry_price=100.0,
            stop_loss=103.0,
            take_profit_1=96.0,
            max_hold=5,
            direction="short",
        )
        assert result["exit_reason"] == "stop"
        assert result["exit_price"] == 103.0
        assert result["return_pct"] == -3.0

    def test_short_take_profit_triggered(self):
        """卖出建议：价格下行达止盈（下方）→ 盈利单。"""
        closes = [100, 100]
        highs = [101, 101]
        lows = [99, 95]  # 第二根跌破下方止盈 96
        result = simulate_advice_trade(
            highs,
            lows,
            closes,
            entry_idx=0,
            entry_price=100.0,
            stop_loss=103.0,
            take_profit_1=96.0,
            max_hold=5,
            direction="short",
        )
        assert result["exit_reason"] == "tp1"
        assert result["exit_price"] == 96.0
        assert result["return_pct"] == 4.0

    def test_short_invalid_shape(self):
        """卖出建议止损低于止盈 → 无效。"""
        result = simulate_advice_trade(
            [101, 101],
            [99, 99],
            [100, 100],
            entry_idx=0,
            entry_price=100.0,
            stop_loss=96.0,
            take_profit_1=103.0,
            max_hold=5,
            direction="short",
        )
        assert result["exit_reason"] == "invalid"

    def test_invalid_advice_shape(self):
        """止损不低于止盈的建议视为无效。"""
        result = simulate_advice_trade(
            [101, 101],
            [99, 99],
            [100, 100],
            entry_idx=0,
            entry_price=100.0,
            stop_loss=105.0,
            take_profit_1=95.0,
            max_hold=5,
        )
        assert result["exit_reason"] == "invalid"

    def test_out_of_range_entry(self):
        """入场索引越界返回 invalid。"""
        result = simulate_advice_trade(
            [101],
            [99],
            [100],
            entry_idx=5,
            entry_price=100.0,
            stop_loss=97.0,
            take_profit_1=104.0,
            max_hold=5,
        )
        assert result["exit_reason"] == "invalid"


class TestSimulateAdviceBatch:
    """批量建议聚合测试。"""

    def test_batch_statistics_structure(self):
        """批量结果包含必要统计字段。"""
        highs = _seq(100, 0.5, 30)
        lows = _seq(99, 0.4, 30)
        closes = _seq(100, 0.5, 30)
        advices = [
            {
                "entry_idx": 0,
                "entry_price": 100.0,
                "stop_loss": 97.0,
                "take_profit_1": 106.0,
                "max_hold": 5,
            },
            {
                "entry_idx": 5,
                "entry_price": 102.5,
                "stop_loss": 99.5,
                "take_profit_1": 108.0,
                "max_hold": 5,
            },
            {
                "entry_idx": 10,
                "entry_price": 105.0,
                "stop_loss": 102.0,
                "take_profit_1": 111.0,
                "max_hold": 5,
            },
        ]
        result = simulate_advice_batch(highs, lows, closes, advices)
        assert result["count"] == 3
        assert 0.0 <= result["win_rate"] <= 1.0
        for key in ("avg_return", "total_return", "stop_rate", "tp_rate", "expire_rate"):
            assert key in result

    def test_invalid_advices_skipped(self):
        """非法建议在批量中被过滤。"""
        highs = _seq(100, 0.5, 10)
        lows = _seq(99, 0.4, 10)
        closes = _seq(100, 0.5, 10)
        advices = [
            {"entry_idx": 0, "entry_price": 100.0, "stop_loss": 97.0, "take_profit_1": 106.0},
            {
                "entry_idx": -1,
                "entry_price": 100.0,
                "stop_loss": 97.0,
                "take_profit_1": 106.0,
            },  # 非法索引
            {
                "entry_idx": 0,
                "entry_price": 0.0,
                "stop_loss": 97.0,
                "take_profit_1": 106.0,
            },  # 非法价格
        ]
        result = simulate_advice_batch(highs, lows, closes, advices)
        assert result["count"] == 1


class TestV102AdviceEndToEnd:
    """用 V102 条件266 生成的 3买 建议跑模拟器。"""

    def test_buy3_advice_replayable(self):
        """BUY_3 生成的入场/止损/止盈建议可在历史序列上回放。"""
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买测试")
        mmd.bi = MagicMock()
        mmd.bi.low = 98.0
        mmd.bi.high = 102.0
        mmd.zs = MagicMock()
        mmd.zs.zg = 105.0
        mmd.zs.zd = 95.0
        closes = [100.0] * 30
        highs = [101.0] * 30
        lows = [99.0] * 30

        advice = _calc_decision_support_enhanced(mmd, closes, highs, lows, None, None)

        assert advice["entry_price"] > 0
        assert advice["stop_loss"] < advice["entry_price"] < advice["take_profit_1"]

        result = simulate_advice_trade(
            closes,
            highs,
            lows,
            entry_idx=10,
            entry_price=advice["entry_price"],
            stop_loss=advice["stop_loss"],
            take_profit_1=advice["take_profit_1"],
            max_hold=10,
        )
        # 亏损单不低于理论最大亏损（止损位），盈利单不高于理论最大盈利（止盈位）
        assert (
            result["return_pct"]
            >= (advice["stop_loss"] - advice["entry_price"]) / advice["entry_price"] * 100 - 0.01
        )
        assert (
            result["return_pct"]
            <= (advice["take_profit_1"] - advice["entry_price"]) / advice["entry_price"] * 100
            + 0.01
        )

    def test_batch_with_v102_advices(self):
        """多笔 V102 建议批量回放输出统计。"""
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买测试")
        mmd.bi = MagicMock()
        mmd.bi.low = 98.0
        mmd.bi.high = 102.0
        mmd.zs = MagicMock()
        mmd.zs.zg = 105.0
        mmd.zs.zd = 95.0
        closes = [100.0] * 40
        highs = [101.0] * 40
        lows = [99.0] * 40

        advices = []
        for idx in (5, 15, 25):
            a = _calc_decision_support_enhanced(mmd, closes, highs, lows, None, None)
            advices.append(
                {
                    "entry_idx": idx,
                    "entry_price": a["entry_price"],
                    "stop_loss": a["stop_loss"],
                    "take_profit_1": a["take_profit_1"],
                    "max_hold": 8,
                }
            )

        result = simulate_advice_batch(closes, highs, lows, advices)
        assert result["count"] == 3
        assert result["avg_return"] != 0.0 or result["expire_rate"] > 0


class TestCollectSignalAdvices:
    """从缠论结果提取可回放建议（collect_signal_advices）。"""

    def _fake_mmd(self, mmd_type: str, idx: int):
        from easy_tdx.chanlun.types import MMD, MMDType

        t = {"buy3": MMDType.BUY_3, "sell3": MMDType.SELL_3}[mmd_type]
        mmd = MMD(mmd_type=t, msg="测试")
        mmd.bi = MagicMock()
        mmd.bi.end = MagicMock()
        mmd.bi.end.k = MagicMock()
        mmd.bi.end.k.k_index = idx
        mmd.bi.low = 98.0
        mmd.bi.high = 102.0
        mmd.zs = MagicMock()
        mmd.zs.zg = 105.0
        mmd.zs.zd = 95.0
        return mmd

    def test_extract_long_and_short(self):
        """3买→long、3卖→short，且信号日窗口生成建议。"""
        from easy_tdx.backtest.advice_simulator import collect_signal_advices

        closes = [100.0] * 60
        highs = [101.0] * 60
        lows = [99.0] * 60
        result = MagicMock()
        result.mmds = [self._fake_mmd("buy3", 10), self._fake_mmd("sell3", 30)]

        advices = collect_signal_advices(result, closes, highs, lows, max_hold=8)

        assert len(advices) == 2
        long_adv = next(a for a in advices if a["direction"] == "long")
        short_adv = next(a for a in advices if a["direction"] == "short")
        assert long_adv["entry_idx"] == 10
        assert long_adv["stop_loss"] < long_adv["entry_price"] < long_adv["take_profit_1"]
        assert short_adv["entry_idx"] == 30
        assert short_adv["stop_loss"] > short_adv["entry_price"] > short_adv["take_profit_1"]

    def test_empty_mmds(self):
        """无 3买/3卖 信号返回空列表。"""
        from easy_tdx.backtest.advice_simulator import collect_signal_advices

        result = MagicMock()
        result.mmds = []
        assert collect_signal_advices(result, [100.0] * 40, [101.0] * 40, [99.0] * 40, 8) == []


class TestAdviceCli:
    """easy-tdx advice CLI 命令。"""

    def test_advice_help(self):
        """advice --help 输出参数说明。"""
        from click.testing import CliRunner

        from easy_tdx.cli.cmd_chanlun import advice_simulate

        runner = CliRunner()
        res = runner.invoke(advice_simulate, ["--help"])
        assert res.exit_code == 0
        assert "MARKET" in res.output
        assert "--max-hold" in res.output
        assert "csv" in res.output  # V329: --output 支持 csv
        assert "回放" in res.output

    def test_offline_advice_help(self):
        """V351: offline advice 子命令（本地 .day 日线 → V102 建议回放）注册可见。"""
        from click.testing import CliRunner

        from easy_tdx.cli.cmd_offline import offline

        runner = CliRunner()
        res = runner.invoke(offline, ["--help"])
        assert res.exit_code == 0
        assert "advice" in res.output
        # 帮助文本说明其用途：无需网络跑 V102 建议回放
        assert "V102" in res.output

    def test_offline_advice_file_option(self):
        """V352: offline advice 支持 --file 直接指定 .day 文件路径（不依赖 TDX_HOME）。"""
        from click.testing import CliRunner

        from easy_tdx.cli.cmd_offline import offline

        runner = CliRunner()
        res = runner.invoke(offline, ["advice", "--help"])
        assert res.exit_code == 0
        assert "--file" in res.output  # V352: 直接指定 .day 文件路径

    def test_offline_advice_batch_help(self):
        """V353: offline advice-batch（离线批量建议实证）注册可见，支持 md 输出。"""
        from click.testing import CliRunner

        from easy_tdx.cli.cmd_offline import offline

        runner = CliRunner()
        res = runner.invoke(offline, ["advice-batch", "--help"])
        assert res.exit_code == 0
        assert "--dir" in res.output
        assert "--limit" in res.output
        assert "md" in res.output  # V353: --output 支持 md 报告

    def test_offline_watch_help(self):
        """V354: offline watch（离线信号监控 + V102 建议摘要）注册可见。"""
        from click.testing import CliRunner

        from easy_tdx.cli.cmd_offline import offline

        runner = CliRunner()
        res = runner.invoke(offline, ["watch", "--help"])
        assert res.exit_code == 0
        assert "--dir" in res.output
        assert "--state" in res.output  # V354: 已见信号状态文件


class TestSummarizeBatch:
    """多标的批量汇总（summarize_batch）。"""

    def test_aggregates_multiple_symbols(self):
        """多标的回放报告聚合为全局统计。"""
        from easy_tdx.backtest.advice_simulator import summarize_batch

        reports = [
            {
                "trades": [
                    {"return_pct": 3.0, "exit_reason": "tp1"},
                    {"return_pct": -2.0, "exit_reason": "stop"},
                ]
            },
            {"trades": [{"return_pct": 1.0, "exit_reason": "expire"}]},
            {"trades": []},  # 无交易标的跳过
        ]
        s = summarize_batch(reports)

        assert s["symbols"] == 2
        assert s["advice_count"] == 3
        assert s["win_rate"] == round(2 / 3, 4)
        assert s["avg_return"] == round((3 - 2 + 1) / 3, 2)
        assert s["positive_symbols"] == 2
        assert s["stop_rate"] == round(1 / 3, 4)
        assert s["tp_rate"] == round(1 / 3, 4)
        assert s["expire_rate"] == round(1 / 3, 4)

    def test_empty_reports(self):
        """无交易时返回零汇总。"""
        from easy_tdx.backtest.advice_simulator import summarize_batch

        s = summarize_batch([{"trades": []}, {"trades": []}])
        assert s["symbols"] == 0
        assert s["advice_count"] == 0
        assert s["win_rate"] == 0.0
