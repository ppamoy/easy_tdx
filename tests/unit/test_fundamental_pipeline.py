"""fundamental/pipeline.py 纯函数测试（V399c）。

覆盖 _returns_at / _sina_frame / _summarize_periods 三个纯函数，离线可测。
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd

from easy_tdx.fundamental.pipeline import _returns_at, _sina_frame, _summarize_periods


class TestReturnsAt:
    def _df(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=5, freq="D"),
                "close": [100.0, 110.0, 121.0, 133.1, 146.41],
            }
        )

    def test_empty(self) -> None:
        assert _returns_at(None, date(2024, 1, 1), (20,)) == {}
        assert _returns_at(pd.DataFrame(), date(2024, 1, 1), (20,)) == {}

    def test_target_after_all_dates(self) -> None:
        assert _returns_at(self._df(), date(2030, 1, 1), (20,)) == {}

    def test_returns(self) -> None:
        out = _returns_at(self._df(), date(2024, 1, 1), (1, 2, 5))
        assert out["as_of_close"] == 100.0
        assert out["ret_1d"] == 10.0
        assert out["ret_2d"] == 21.0
        assert out["ret_5d"] is None  # 越界


class TestSinaFrame:
    def test_build(self) -> None:
        rows = [
            SimpleNamespace(
                code="000001",
                market="SZ",
                report_date=date(2024, 3, 31),
                disclosure_date=date(2024, 4, 25),
                indicators={"roe": 15.0, "eps": 1.2},
            ),
        ]
        df = _sina_frame(rows)
        assert df.iloc[0]["code"] == "000001"
        assert df.iloc[0]["roe"] == 15.0
        assert df.iloc[0]["eps"] == 1.2


class TestSummarizePeriods:
    def test_empty(self) -> None:
        out = _summarize_periods([], (20, 60))
        assert out["overall"]["count"] == 0
        assert out["by_category"]["tree"]["count"] == 0

    def test_with_data(self) -> None:
        periods = [
            {
                "results": [
                    {"category": "tree", "performance": {"ret_20d": 5.0, "ret_60d": 10.0}},
                    {"category": "grain", "performance": {"ret_20d": -2.0, "ret_60d": 3.0}},
                ],
                "index": {"ret_20d": 1.0, "ret_60d": 4.0},
            }
        ]
        out = _summarize_periods(periods, (20, 60))
        assert out["overall"]["count"] == 2
        assert out["overall"]["ret_20d"]["avg"] == 1.5
        assert out["beats_index"]["ret_20d"]["beats"] is True
