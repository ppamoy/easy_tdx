"""web/routers/backtest.py _run_optimize 测试（V415）。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from easy_tdx.web.backtest_schemas import OptimizeBacktestRequest
from easy_tdx.web.routers.backtest import _run_optimize


def _df(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(5)
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


class TestRunOptimize:
    def test_grid_search(self) -> None:
        req = OptimizeBacktestRequest(
            strategy="ma_cross",
            param_grid={"fast": [5, 10], "slow": [20]},
            ohlcv=[
                {
                    "datetime": "2024-01-01",
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10.5,
                    "vol": 100,
                    "amount": 1000,
                }
            ],
        )
        result = _run_optimize(_df(), req)
        assert "best" in result or "results" in result

    def test_walk_forward(self) -> None:
        req = OptimizeBacktestRequest(
            strategy="ma_cross",
            param_grid={"fast": [5, 10], "slow": [20]},
            use_walk_forward=True,
            ohlcv=[
                {
                    "datetime": "2024-01-01",
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10.5,
                    "vol": 100,
                    "amount": 1000,
                }
            ],
        )
        result = _run_optimize(_df(), req)
        assert "best" in result or "results" in result
