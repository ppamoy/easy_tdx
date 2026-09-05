"""web/routers/backtest.py _run_portfolio_backtest 测试（V417）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from easy_tdx.backtest.portfolio_engine import StockData
from easy_tdx.web.backtest_schemas import PortfolioBacktestRequest
from easy_tdx.web.routers.backtest import _run_portfolio_backtest


def _df(seed: int, n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
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


def _stocks() -> list[StockData]:
    return [
        StockData(code="000001", market="SZ", df=_df(1)),
        StockData(code="600000", market="SH", df=_df(2)),
    ]


class TestRunPortfolioBacktest:
    def test_unknown_strategy(self) -> None:
        req = PortfolioBacktestRequest(strategy="nope", stocks=["SZ:000001"])
        with pytest.raises(ValueError, match="未知策略"):
            _run_portfolio_backtest(_stocks(), req)

    def test_full_run(self) -> None:
        req = PortfolioBacktestRequest(strategy="ma_cross", stocks=["SZ:000001", "SH:600000"])
        result = _run_portfolio_backtest(_stocks(), req)
        assert "total_performance" in result
