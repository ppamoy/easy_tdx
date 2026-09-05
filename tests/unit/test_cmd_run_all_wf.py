"""cli/cmd_run_all.py _compute_walk_forward_single 测试（V401）。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from easy_tdx.backtest.strategies.registry import get_registry
from easy_tdx.cli.cmd_run_all import _compute_walk_forward_single


def _df(n: int) -> pd.DataFrame:
    rng = np.random.default_rng(7)
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


class TestComputeWalkForward:
    def test_short_data_returns_none(self) -> None:
        cls = get_registry().get("ma_cross").strategy_cls
        assert _compute_walk_forward_single(_df(50), cls, 1e6, 0.0003) is None

    def test_full_run(self) -> None:
        cls = get_registry().get("ma_cross").strategy_cls
        report = _compute_walk_forward_single(_df(200), cls, 1e6, 0.0003)
        assert report is not None
        assert "windows" in report
        assert "verdict" in report
