"""信号前瞻命中率与模型准确度验证的单元测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from easy_tdx.backtest.signal_accuracy import (
    _datetime_to_int,
    compute_signal_accuracy,
    compute_signal_accuracy_by_type,
)


def _make_df(closes: list[float]) -> pd.DataFrame:
    """构造最简 OHLCV（close 决定收益，open/high/low 沿 close 展开）。"""
    dates = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": c - 0.1,
            "high": c + 0.2,
            "low": c - 0.3,
            "close": c,
            "vol": 1_000_000,
            "amount": 1_000_000.0,
        }
    )


def _trades(buy_dts: list[int], sell_dts: list[int] | None = None) -> pd.DataFrame:
    """构造成交记录 DataFrame（与引擎 _trades_to_df 同列）。"""
    rows: list[dict] = []
    for dt in buy_dts:
        rows.append(
            {
                "datetime": dt,
                "direction": "BUY",
                "size": 100,
                "price": 10.0,
                "commission": 0.0,
                "slippage": 0.0,
                "pnl": 0.0,
                "cost_basis": 0.0,
                "rejected": False,
            }
        )
    for dt in sell_dts or []:
        rows.append(
            {
                "datetime": dt,
                "direction": "SELL",
                "size": 100,
                "price": 10.0,
                "commission": 0.0,
                "slippage": 0.0,
                "pnl": 0.0,
                "cost_basis": 0.0,
                "rejected": False,
            }
        )
    return pd.DataFrame(rows)


class TestDatetimeToInt:
    def test_pandas_timestamps(self) -> None:
        arr = pd.to_datetime(["2024-01-05", "2024-12-31"]).to_numpy()
        out = _datetime_to_int(arr)
        assert out.tolist() == [20240105, 20241231]

    def test_int_input_passthrough(self) -> None:
        out = _datetime_to_int(np.asarray([20240105, 20241231]))
        assert out.tolist() == [20240105, 20241231]

    def test_empty(self) -> None:
        assert _datetime_to_int(np.asarray([])).tolist() == []


class TestComputeSignalAccuracy:
    def test_empty_inputs(self) -> None:
        report = compute_signal_accuracy(pd.DataFrame(), pd.DataFrame())
        assert report["buy"] is None
        assert report["sell"] is None
        assert report["verdict"]  # 非空提示语

    def test_no_trades(self) -> None:
        df = _make_df([10.0] * 30)
        report = compute_signal_accuracy(df, _trades([]))
        assert report["buy"] is None
        assert report["sell"] is None
        assert "无买入" in report["verdict"] or "无成交" in report["verdict"]

    def test_missing_close_column(self) -> None:
        df = pd.DataFrame({"datetime": ["20240101"]})
        report = compute_signal_accuracy(df, _trades([20240102]))
        assert "close" in report.get("note", "")

    def test_uptrend_buy_all_hit(self) -> None:
        # 单调上涨：任何买入前瞻 5 根都是正收益 → 命中率 100%
        closes = [100 + i * 1.0 for i in range(60)]
        df = _make_df(closes)
        # 买入发生在第 5 / 15 / 25 根（对应索引）
        trades = _trades([20240106, 20240116, 20240126])
        report = compute_signal_accuracy(df, trades)
        buy = report["buy"]
        assert buy is not None
        assert buy["signals"] == 3
        h5 = buy["horizons"]["5"]
        assert h5["count"] == 3
        assert h5["hit_rate"] == pytest.approx(1.0)
        assert h5["avg_return"] > 0
        # 超额命中率 = 1 - 随机基准命中率 >= 0
        assert h5["excess_hit_rate"] >= 0.0
        assert 0.0 <= h5["baseline_hit_rate"] <= 1.0

    def test_downtrend_buy_miss(self) -> None:
        # 单调下跌：买入前瞻 5 根均为负收益 → 命中率 0
        closes = [100 - i * 1.0 for i in range(60)]
        df = _make_df(closes)
        trades = _trades([20240106, 20240116])
        report = compute_signal_accuracy(df, trades)
        buy = report["buy"]
        assert buy is not None
        h5 = buy["horizons"]["5"]
        assert h5["hit_rate"] == pytest.approx(0.0)
        assert h5["avg_return"] < 0
        assert h5["excess_hit_rate"] <= 0.0

    def test_sell_signal_downtrend_hit(self) -> None:
        # 卖出方向：下跌为命中。卖出后 5 根下跌 → 命中率 100%
        closes = [100 - i * 1.0 for i in range(60)]
        df = _make_df(closes)
        trades = _trades([20240106], sell_dts=[20240116])
        report = compute_signal_accuracy(df, trades)
        sell = report["sell"]
        assert sell is not None
        h5 = sell["horizons"]["5"]
        assert h5["hit_rate"] == pytest.approx(1.0)
        assert h5["avg_return"] > 0  # 卖出回避了下跌，折算正收益

    def test_sell_baseline_aligned_to_downside(self) -> None:
        """V502: 卖出基准应对齐到下跌方向（随机空仓避跌命中 = 1 - P(上涨)）。

        单调下跌市里，随机空仓的避跌命中率 ≈ 1.0（几乎所有窗口都下跌），
        因此卖点 100% 命中相对基准的超额应 ≈ 0，而非旧实现的 1.0。
        """
        closes = [100 - i * 1.0 for i in range(60)]
        df = _make_df(closes)
        trades = _trades([], sell_dts=[20240116])
        report = compute_signal_accuracy(df, trades)
        sell = report["sell"]
        assert sell is not None
        h5 = sell["horizons"]["5"]
        assert h5["hit_rate"] == pytest.approx(1.0)
        assert h5["baseline_hit_rate"] == pytest.approx(1.0, abs=0.05)
        assert abs(h5["excess_hit_rate"]) < 0.1
        # 随机空仓在下跌市折算正收益 → 卖出基准收益应为正
        assert h5["baseline_avg_return"] > 0

    def test_benchmark_buy_hold_and_alpha(self) -> None:
        closes = [100 + i for i in range(50)]
        df = _make_df(closes)
        trades = _trades([20240106, 20240120])
        report = compute_signal_accuracy(df, trades, strategy_total_return=0.80)
        bench = report["benchmark"]
        # 买入持有 = 149/100 - 1 = 0.49
        assert bench["buy_hold_return"] == pytest.approx(0.49, abs=1e-9)
        assert bench["strategy_return"] == pytest.approx(0.80)
        assert bench["alpha"] == pytest.approx(0.80 - 0.49, abs=1e-9)

    def test_small_data_falls_back_to_full_baseline(self) -> None:
        # 数据量 < RANDOM_SAMPLES 时随机基准直接用全部可入场 bar（不抛错）
        df = _make_df([10.0, 11.0, 12.0, 13.0, 14.0, 15.0])
        trades = _trades([20240102])
        report = compute_signal_accuracy(df, trades, horizons=(1, 3, 5))
        assert report["buy"] is not None
        h3 = report["buy"]["horizons"]["3"]
        assert h3["count"] >= 1
        assert h3["baseline_hit_rate"] == pytest.approx(1.0)

    def test_verdict_present(self) -> None:
        df = _make_df([100 + i for i in range(60)])
        report = compute_signal_accuracy(df, _trades([20240106, 20240116, 20240126]))
        assert isinstance(report["verdict"], str)
        assert len(report["verdict"]) > 0

    def test_engine_result_carries_signal_accuracy(self) -> None:
        # 集成验证：BacktestEngine.run 结果含 signal_accuracy 字段
        from easy_tdx import MyTT
        from easy_tdx.backtest.engine import BacktestEngine
        from easy_tdx.backtest.strategy import Strategy

        class MA5Strategy(Strategy):
            def init(self) -> None:
                self.ma5 = self.I(MyTT.MA, self.data.close, 5)

            def next(self) -> None:
                if self._bar_index == 10:
                    self.buy(size=0)
                elif self._bar_index == 20:
                    self.sell(size=0)

        df = _make_df([100 + i * 0.5 for i in range(60)])
        engine = BacktestEngine(MA5Strategy, cash=100000)
        result = engine.run(df)
        assert result.signal_accuracy is not None
        assert result.signal_accuracy["buy"] is not None
        assert result.signal_accuracy["benchmark"]["buy_hold_return"] > 0
        d = result.to_dict()
        assert "signal_accuracy" in d
        assert d["signal_accuracy"]["buy"] is not None


class TestSignalAccuracyByType:
    """按信号类型分组的前瞻命中率验证（缠论买卖点场景）。"""

    def test_uptrend_buy_signals_hit(self) -> None:
        # 单调上涨市：1buy/2buy 买点未来 5 根全涨 → 命中率 100%
        closes = [100 + i * 0.5 for i in range(80)]
        signals = [
            {"type": "1buy", "bar_index": 10},
            {"type": "1buy", "bar_index": 30},
            {"type": "2buy", "bar_index": 20},
        ]
        rep = compute_signal_accuracy_by_type(closes, signals)
        assert "1buy" in rep["by_type"]
        assert "2buy" in rep["by_type"]
        buy1 = rep["by_type"]["1buy"]
        assert buy1["signals"] == 2
        h5 = buy1["horizons"]["5"]
        assert h5["hit_rate"] == pytest.approx(1.0)
        assert h5["avg_return"] > 0
        # 排名：1buy 排在最前（超额命中率相同则按输入稳定性，至少都在榜）
        assert any(r["type"] == "1buy" for r in rep["ranking"])

    def test_downtrend_sell_signals_hit(self) -> None:
        # 单调下跌市：1sell 卖点回避下跌 → 命中率 100%（下跌为命中）
        closes = [100 - i * 0.5 for i in range(80)]
        signals = [{"type": "1sell", "bar_index": 10}, {"type": "1sell", "bar_index": 30}]
        rep = compute_signal_accuracy_by_type(closes, signals)
        sell1 = rep["by_type"]["1sell"]
        h5 = sell1["horizons"]["5"]
        assert h5["hit_rate"] == pytest.approx(1.0)
        assert sell1["direction"] == "SELL"

    def test_sell_type_baseline_aligned_to_downside(self) -> None:
        """V503: 卖点类型的基准对齐下跌方向（随机空仓避跌命中 = 1 - P(涨)）。

        下跌市里随机空仓避跌命中率 ≈ 1.0，卖点 100% 命中的超额应 ≈ 0。
        """
        closes = [100 - i * 0.5 for i in range(80)]
        signals = [{"type": "1sell", "bar_index": 10}, {"type": "1sell", "bar_index": 30}]
        rep = compute_signal_accuracy_by_type(closes, signals)
        sell1 = rep["by_type"]["1sell"]
        h5 = sell1["horizons"]["5"]
        assert h5["hit_rate"] == pytest.approx(1.0)
        assert h5["baseline_hit_rate"] == pytest.approx(1.0, abs=0.05)
        assert abs(h5["excess_hit_rate"]) < 0.1

    def test_sell_signal_hit_uses_downside(self) -> None:
        # 卖点命中定义 = 未来下跌；上涨则 miss
        closes = [100 + i for i in range(40)]
        signals = [{"type": "2sell", "bar_index": 5}]
        rep = compute_signal_accuracy_by_type(closes, signals)
        sell2 = rep["by_type"]["2sell"]
        h5 = sell2["horizons"]["5"]
        assert h5["hit_rate"] == pytest.approx(0.0)  # 上涨市卖出=误杀
        assert h5["avg_return"] < 0  # 折算收益为负

    def test_empty_and_insufficient(self) -> None:
        rep = compute_signal_accuracy_by_type([1.0, 2.0], [])
        assert rep["by_type"] == {}
        assert rep["ranking"] == []

    def test_bar_index_out_of_range_skipped(self) -> None:
        closes = [100 + i for i in range(20)]
        signals = [{"type": "1buy", "bar_index": 18}]  # 18+5 >= 20 → 被跳过
        rep = compute_signal_accuracy_by_type(closes, signals)
        h5 = rep["by_type"]["1buy"]["horizons"]["5"]
        assert h5["count"] == 0

    def test_summary_present(self) -> None:
        closes = [100 + i * 0.5 for i in range(80)]
        signals = [{"type": "1buy", "bar_index": 10}, {"type": "1buy", "bar_index": 30}]
        rep = compute_signal_accuracy_by_type(closes, signals)
        assert isinstance(rep["summary"], str)
        assert len(rep["summary"]) > 0

    def test_verdict_per_type(self) -> None:
        closes = [100 - i for i in range(60)]
        signals = [{"type": "3sell", "bar_index": 10}]
        rep = compute_signal_accuracy_by_type(closes, signals)
        # V503: 下跌市里卖点 100% 命中但与随机空仓相当（非「显著优于随机」）
        verdict = rep["by_type"]["3sell"]["verdict"]
        assert "卖出点" in verdict
        assert "随机" in verdict
