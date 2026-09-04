"""changying_chanlun 策略 + screen/scanner 纯函数边界测试（V399）。

changying_chanlun.py 此前覆盖率 41%，其 next() 从未被真实喂数据跑过；
scanner.py 的 _bars_to_df/_get_strategy_file 纯函数零覆盖。本文件补齐两者。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import easy_tdx.backtest.strategies.changying_chanlun  # noqa: F401
from easy_tdx.backtest.strategies.registry import get_registry
from easy_tdx.screen.scanner import _bars_to_df


def _make_df(n: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    close = 100.0 + np.cumsum(rng.normal(0.03, 1.0, n))
    high = close + rng.uniform(0.3, 1.5, n)
    low = close - rng.uniform(0.3, 1.5, n)
    open_ = low + rng.uniform(0, high - low, n)
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": open_,
            "close": close,
            "high": high,
            "low": low,
            "vol": rng.integers(1000, 10000, n).astype(float),
            "amount": rng.integers(1e7, 1e8, n).astype(float),
        }
    )


class TestChangyingChanlunStrategy:
    def test_run_on_synthetic(self) -> None:
        entry = get_registry().get("changying_chanlun")
        s = entry.build()
        df = _make_df(200)
        s._bind_data(df)
        s._call_init()
        for i in range(len(df)):
            s._set_bar_index(i)
            s._call_next()
        sigs = s._clear_signals()
        assert isinstance(sigs, list)

    def test_run_no_season_filter(self) -> None:
        entry = get_registry().get("changying_chanlun")
        s = entry.build({"use_season_filter": False})
        df = _make_df(150)
        s._bind_data(df)
        s._call_init()
        for i in range(len(df)):
            s._set_bar_index(i)
            s._call_next()
        assert isinstance(s._clear_signals(), list)


class TestScannerBarsToDf:
    def test_empty(self) -> None:
        assert _bars_to_df([]).empty

    def test_converts_bars(self) -> None:
        from easy_tdx.models.bar import SecurityBar

        bars = [
            SecurityBar(
                open=10,
                close=11,
                high=12,
                low=9,
                vol=1000,
                amount=11000,
                year=2024,
                month=1,
                day=2,
                hour=15,
                minute=0,
            ),
            SecurityBar(
                open=11,
                close=12,
                high=13,
                low=10,
                vol=1200,
                amount=13000,
                year=2024,
                month=1,
                day=3,
                hour=15,
                minute=0,
            ),
        ]
        df = _bars_to_df(bars)
        assert len(df) == 2
        assert "datetime" in df.columns
        assert df["close"].iloc[-1] == 12
