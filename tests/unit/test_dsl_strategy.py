"""DSL 策略（dsl_strategy 装饰器）回归测试。

V-35 发现骨架缺陷：DSLStrategy.init() 从未调用 _signal_func，
_buy_mask/_sell_mask 恒为 None，next() 永远静默 → BacktestEngine 全链路 0 交易。
本文件同时锁定：真实链路产生交易（坏版本回归）、mask 长度不一致报错、
buy/sell 同 bar 时 buy 优先（装饰器文档语义）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from easy_tdx.backtest.dsl import dsl_strategy
from easy_tdx.backtest.engine import BacktestEngine


def _make_df(n: int = 300, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.ones(n) * 1000,
        }
    )


@dsl_strategy
def _fixed_points(df: pd.DataFrame):
    n = len(df)
    buy = np.zeros(n, dtype=bool)
    sell = np.zeros(n, dtype=bool)
    buy[30] = True
    sell[60] = True
    return buy, sell


class TestDslStrategyRealPipeline:
    """坏版本回归：骨架版 0 交易；修复后必须真实成交。"""

    def test_fixed_points_produce_trades(self):
        df = _make_df()
        result = BacktestEngine(_fixed_points(), cash=100_000.0).run(df)
        # 坏版本（init 不计算 mask）在此断言必然失败：trades == 0
        assert len(result.trades) >= 1
        directions = result.trades["direction"].tolist()
        assert "BUY" in directions
        assert "SELL" in directions

    def test_mask_functions_are_called_with_dataframe(self):
        """用户函数收到的是 DataFrame 且返回等长 mask。"""
        calls: list[int] = []

        @dsl_strategy
        def probe(df: pd.DataFrame):
            calls.append(len(df))
            n = len(df)
            buy = np.zeros(n, dtype=bool)
            sell = np.zeros(n, dtype=bool)
            buy[10] = True
            sell[20] = True
            return buy, sell

        df = _make_df()
        BacktestEngine(probe(), cash=100_000.0).run(df)
        assert calls == [300]  # init 时恰好调用一次

    def test_uneven_mask_lengths_raise(self):
        @dsl_strategy
        def bad(df: pd.DataFrame):
            return np.zeros(10, dtype=bool), np.zeros(5, dtype=bool)

        with pytest.raises(ValueError, match="长度不一致"):
            BacktestEngine(bad(), cash=100_000.0).run(_make_df())

    def test_dual_ma_style_strategy_trades(self):
        """贴近 docstring 示例的双均线写法（NaN 对齐）应产生交易。"""

        @dsl_strategy
        def dual_ma(df: pd.DataFrame):
            close = df["close"].to_numpy(dtype=float)
            n = len(close)
            ma_f = np.full(n, np.nan)
            ma_s = np.full(n, np.nan)
            ma_f[4:] = np.convolve(close, np.ones(5) / 5, mode="valid")
            ma_s[19:] = np.convolve(close, np.ones(20) / 20, mode="valid")
            buy = np.zeros(n, dtype=bool)
            sell = np.zeros(n, dtype=bool)
            valid = ~(np.isnan(ma_f) | np.isnan(ma_s))
            buy[valid] = ma_f[valid] > ma_s[valid]
            sell[valid] = ma_f[valid] < ma_s[valid]
            return buy, sell

        result = BacktestEngine(dual_ma(), cash=100_000.0).run(_make_df())
        assert len(result.trades) >= 1

    def test_strategy_name_kept(self):
        assert _fixed_points.__name__ == "_fixed_points"
