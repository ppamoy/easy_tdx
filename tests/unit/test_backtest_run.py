"""web/routers/backtest.py _run_backtest 测试（V414）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from easy_tdx.web.backtest_schemas import BacktestRequest
from easy_tdx.web.routers.backtest import _run_backtest


def _df(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(3)
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


class TestRunBacktest:
    def test_unknown_strategy(self) -> None:
        req = BacktestRequest(strategy="definitely_not_a_strategy", symbol="SH:600000")
        with pytest.raises(ValueError, match="未知策略"):
            _run_backtest(_df(), req)

    def test_full_run(self) -> None:
        req = BacktestRequest(strategy="ma_cross", symbol="SH:600000")
        result = _run_backtest(_df(), req)
        assert "performance" in result
        assert "model_trust" in result
