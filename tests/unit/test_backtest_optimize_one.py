"""web/routers/backtest.py _optimize_one_strategy 测试（V416）。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from easy_tdx.web.routers.backtest import _optimize_one_strategy


def _df(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(9)
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


class TestOptimizeOneStrategy:
    def test_unknown_strategy_raises(self) -> None:
        import pytest

        with pytest.raises(KeyError):
            _optimize_one_strategy(
                "definitely_not_a_strategy",
                {"fast": [5, 10]},
                _df(),
                1e6,
                0.0003,
                0.0,
                "next_open",
            )

    def test_valid_strategy(self) -> None:
        out = _optimize_one_strategy(
            "ma_cross",
            {"fast": [5, 10], "slow": [20]},
            _df(),
            1e6,
            0.0003,
            0.0,
            "next_open",
        )
        assert out is not None
        assert out["strategy"] == "ma_cross"
        assert "params" in out
        assert "total_return" in out
