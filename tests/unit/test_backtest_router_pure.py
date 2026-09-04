"""web/routers/backtest.py 纯函数测试（V399i）。

覆盖 _ohlcv_to_df / _filter_df_by_date / _now，离线可测。
"""

from __future__ import annotations

import pandas as pd
import pytest

from easy_tdx.web.routers.backtest import _filter_df_by_date, _now, _ohlcv_to_df


def _records(n: int = 5) -> list[dict]:
    return [
        {
            "datetime": f"2024-01-{i + 1:02d}",
            "open": 10 + i,
            "high": 11 + i,
            "low": 9 + i,
            "close": 10.5 + i,
            "vol": 100 + i,
            "amount": 1000 + i,
        }
        for i in range(n)
    ]


class TestOhlcvToDf:
    def test_convert(self) -> None:
        df = _ohlcv_to_df(_records(3))
        assert len(df) == 3
        assert pd.api.types.is_datetime64_any_dtype(df["datetime"])

    def test_missing_column(self) -> None:
        rec = _records(2)
        for r in rec:
            r.pop("amount")
        with pytest.raises(ValueError, match="缺少必需列"):
            _ohlcv_to_df(rec)

    def test_too_short(self) -> None:
        with pytest.raises(ValueError, match="至少需要 2 根"):
            _ohlcv_to_df(_records(1))


class TestFilterByDate:
    def _df(self) -> pd.DataFrame:
        return pd.DataFrame(
            {"datetime": pd.to_datetime(["2024-01-01", "2024-01-05", "2024-02-01"])}
        )

    def test_no_filter(self) -> None:
        df = self._df()
        assert len(_filter_df_by_date(df, None, None)) == 3

    def test_start(self) -> None:
        df = self._df()
        out = _filter_df_by_date(df, "2024-01-05", None)
        assert len(out) == 2

    def test_end(self) -> None:
        df = self._df()
        out = _filter_df_by_date(df, None, "2024-01-05")
        assert len(out) == 2

    def test_both(self) -> None:
        df = self._df()
        out = _filter_df_by_date(df, "2024-01-05", "2024-01-05")
        assert len(out) == 1


class TestNow:
    def test_now(self) -> None:
        t = _now()
        assert t > 0
